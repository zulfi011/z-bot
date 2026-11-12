"""One coin's own full search for the trend exit: every EMA length x arm point x stop x switch.

The deployed rule is unchanged on the entry side (5-minute signals, 7-day average, +-0.5% zone from below,
bullish confirmation within 30 minutes, no entries 06:00-12:00 UTC, avoid-strong-bearish). What is searched is
everything after the buy:

  arm      the trade must first be up this much before the trend exit takes over (deployed 1.315%)
  exit     either the deployed style - give back X% of the open profit - or hold until a 1-minute close
           below an EMA of 30 minutes up to 24 hours
  stop     protective stop from the fill (deployed 3.5%)
  switch   EMA hold always, or only when 7d > 15d > 30d at entry with the giveback used otherwise

Honest fill: an EMA exit is filled at the NEXT minute's open after the close that broke the EMA, not at the
same minute. $300 as 3 x $100 lots, both fee levels.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import live_ema_hold_all as live
import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import sol_trend_ride as ride
import stage3_replay as replay

COIN = (sys.argv[1] if len(sys.argv) > 1 else "eth").lower()
EMAS = [30, 45, 60, 90, 120, 180, 240, 300, 360, 480, 600, 720, 960, 1200, 1440, 2160, 2880]
ACTIVATIONS = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
STOPS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
GIVEBACKS = [10.0, 20.0, 30.0, 40.0, 50.0]
WF = ride.WF


def next_below(close, ema):
    """For each minute, the next minute (>= it) whose close is below the EMA; len(close) if never."""
    n = len(close)
    out = np.full(n + 1, n, dtype=np.int64)
    below = close < ema
    for i in range(n - 1, -1, -1):
        out[i] = i if below[i] else out[i + 1]
    return out


def main() -> None:
    global ACTIVATIONS, STOPS, GIVEBACKS
    rule = live.load_rule(COIN)
    # always include the deployed settings so the live rule itself is one of the combinations
    ACTIVATIONS = sorted(set(ACTIVATIONS) | {rule["activation_pct"]})
    STOPS = sorted(set(STOPS) | {rule["stop_pct"]})
    GIVEBACKS = sorted(set(GIVEBACKS) | {rule["giveback_pct"]})
    raw = replay.load_raw(rule["symbol"], include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.SLIP = ride.SLIP
    last = len(grid.OPEN) - 1
    times = pd.DatetimeIndex(raw.open_time)
    entries = live.live_entries(raw, rule)
    bullish = live.regime_flags(raw)
    emas = {span: pd.Series(grid.CLOSE).ewm(span=span, adjust=False).mean().to_numpy() for span in EMAS}
    crossings = {span: next_below(grid.CLOSE, emas[span]) for span in EMAS}
    print(f"{COIN.upper()}: {len(entries)} live signals, {100 * bullish[entries].mean():.0f}% in a clean uptrend", flush=True)

    columns = [("giveback", give, act, stop, None) for stop in STOPS for act in ACTIVATIONS for give in GIVEBACKS]
    columns += [(switch, span, act, stop, None) for switch in ("ema_always", "ema_uptrend")
                for stop in STOPS for act in ACTIVATIONS for span in EMAS]
    cols = len(columns)
    idx = np.full((len(entries), cols), -1, dtype=np.int64)
    price = np.full((len(entries), cols), np.nan)
    code = np.zeros((len(entries), cols), dtype=np.int8)
    print(f"{cols} exit combinations", flush=True)

    for row, entry in enumerate(entries):
        entry = int(entry)
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        arms = {act: research.first_hit(entry, fill * (1 + act / 100), True) for act in ACTIVATIONS}
        stop_levels = {stop: fill * (1 - stop / 100) for stop in STOPS}
        first_stop = {stop: research.first_hit(entry, stop_levels[stop], False) for stop in STOPS}
        later_stop = {}
        trails = {}
        for column, (kind, value, act, stop, _) in enumerate(columns):
            armed, stopped, level = arms[act], first_stop[stop], stop_levels[stop]
            if stopped >= 0 and (armed < 0 or stopped <= armed):
                idx[row, column] = stopped
                price[row, column] = min(level, grid.OPEN[stopped])
                code[row, column] = 2
                continue
            if armed < 0:
                continue
            use_ema = kind == "ema_always" or (kind == "ema_uptrend" and bullish[entry])
            if not use_ema:
                give = value if kind == "giveback" else rule["giveback_pct"]
                key = (act, give)
                if key not in trails:
                    trails[key] = research.trail_exit(armed, fill, give)
                hit, hit_price = trails[key]
                if hit >= 0:
                    idx[row, column] = hit
                    price[row, column] = min(hit_price, grid.OPEN[hit])
                    code[row, column] = 1
                continue
            broke = crossings[value][armed + 1]
            if (act, stop) not in later_stop:
                later_stop[(act, stop)] = research.first_hit(armed + 1, level, False)
            stop_after = later_stop[(act, stop)]
            if stop_after >= 0 and stop_after <= broke:
                idx[row, column] = stop_after
                price[row, column] = min(level, grid.OPEN[stop_after])
                code[row, column] = 2
            elif broke <= last:
                out = min(broke + 1, last)
                idx[row, column] = out
                price[row, column] = grid.OPEN[out]
                code[row, column] = 1

    research.TABLE, research.COLS = (idx, price, code), cols
    research.LOT, research.LOTS, research.INITIAL = 100.0, 3, 300.0
    frames = []
    for fee_bps, fee_name in ((10.0, "USDT"), (7.5, "BNB")):
        grid.FEE = fee_bps / 10_000
        stats = {}
        for name, (start, end) in research.WINDOWS.items():
            mask = (times[entries] >= start) & (times[entries] < end)
            stats[name] = research.simulate(entries[mask], np.flatnonzero(mask))
        block = pd.DataFrame(columns, columns=["style", "value", "arm_pct", "stop_pct", "_"]).drop(columns="_")
        block["fees"] = fee_name
        for name in research.WINDOWS:
            for stat in ("trades", "wins", "profit", "dd", "gross_win", "gross_loss"):
                block[f"{name}_{stat}"] = stats[name][stat]
        frames.append(block)
    board = pd.concat(frames, ignore_index=True)
    board.to_parquet(grid.ROOT / "results" / f"{COIN}_ema_exit_grid_wf.parquet", index=False)
    print(f"saved {len(board):,} rows", flush=True)


if __name__ == "__main__":
    main()
