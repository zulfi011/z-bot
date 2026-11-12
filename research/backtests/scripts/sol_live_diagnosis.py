"""The live SOL rule, taken apart: where the money is lost, and is there really an uptrend being left behind?

Live rule (sol_strategy.json): 12-day average touched from below, bullish 3-minute candle confirms within
30 minutes, skip 06:00-12:00 UTC, skip when 7d < 15d < 30d, stop -2%, trail armed at +1.251% giving back 12%.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

STRATEGY = replay.ROOT.parent.parent / "engine" / "sol_strategy.json"
STOP, ACTIVATION, GIVEBACK = 2.0, 1.251, 12.0


def live_entries(raw, strategy):
    """Exactly the signals the live engine would raise, as 1-minute indices."""
    averages = replay.daily_averages(raw)
    minutes = int(strategy["market"]["signal_timeframe"].removesuffix("m"))
    candles = replay.signal_candles(raw, minutes, averages, int(strategy["averages"]["signal_average_days"]))
    signals, diagnostics = replay.generate_signals(strategy, candles)
    times = pd.DatetimeIndex(raw.open_time)
    blocked = strategy["entry"].get("blocked_entry_hours_utc")
    entries = []
    for signal in signals:
        stamp = pd.Timestamp(signal["entry_time"], tz="UTC")
        if blocked and blocked["start"] <= stamp.hour < blocked["end"]:
            continue
        position = times.searchsorted(stamp)
        if 0 <= position < len(raw) - 1:
            entries.append(int(position))
    return np.array(sorted(set(entries)), dtype=np.int64), diagnostics


def outcome(entry, stop=STOP, activation=ACTIVATION, giveback=GIVEBACK):
    """(exit index, exit price, kind) for one entry: 'stop', 'trail' or 'open'."""
    fill = grid.OPEN[entry] * (1 + grid.SLIP)
    armed = research.first_hit(entry, fill * (1 + activation / 100), True)
    horizon = None if armed < 0 else armed
    stopped = research.first_hit(entry, fill * (1 - stop / 100), False, horizon)
    if stopped >= 0 and (armed < 0 or stopped <= armed):
        return stopped, min(fill * (1 - stop / 100), grid.OPEN[stopped]), "stop", armed
    if armed >= 0:
        index, price = research.trail_exit(armed, fill, giveback)
        if index >= 0:
            return index, price, "trail", armed
    return -1, np.nan, "open", armed


def main() -> None:
    strategy = json.loads(STRATEGY.read_text())
    raw = replay.load_raw("SOLUSDT", include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.FEE = 7.5 / 10_000
    times = pd.DatetimeIndex(raw.open_time)
    entries, diagnostics = live_entries(raw, strategy)
    print(f"live signal engine: {diagnostics}")
    inside = entries[(times[entries] >= research.WINDOWS["full"][0]) & (times[entries] < research.WINDOWS["full"][1])]
    print(f"{len(entries)} signals in the file, {len(inside)} inside the study window\n")

    rows = []
    for entry in entries:
        index, price, kind, armed = outcome(entry)
        if index < 0:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        net = (price * (1 - grid.SLIP) * (1 - grid.FEE)) / (fill * (1 + grid.FEE)) - 1
        peak = float(grid.HIGH[entry:index + 1].max())
        rows.append({"entry_time": times[entry], "entry": entry, "exit": index, "kind": kind,
                     "net_pct": net * 100, "hold_h": (index - entry) / 60,
                     "peak_pct": (peak / fill - 1) * 100,
                     "left_behind_pct": (peak / fill - 1) * 100 - net * 100})
    trades = pd.DataFrame(rows)
    window = trades[(trades.entry_time >= research.WINDOWS["full"][0]) & (trades.entry_time < research.WINDOWS["full"][1])]
    pd.set_option("display.width", 220)

    print("=== every trade, by how it ended (study window, BNB fees, % per trade)")
    print(window.groupby("kind").agg(trades=("net_pct", "size"), avg_pct=("net_pct", "mean"),
        median_pct=("net_pct", "median"), worst_pct=("net_pct", "min"), best_pct=("net_pct", "max"),
        avg_hold_h=("hold_h", "mean"), total_pct=("net_pct", "sum")).round(2).to_string())
    wins, losses = window[window.net_pct > 0], window[window.net_pct <= 0]
    print(f"\nwin rate {100 * len(wins) / len(window):.0f}%  |  average win {wins.net_pct.mean():+.2f}%  "
          f"|  average loss {losses.net_pct.mean():+.2f}%  |  ratio {abs(wins.net_pct.mean() / losses.net_pct.mean()):.2f}x")
    print(f"sum of wins {wins.net_pct.sum():+.1f}%  |  sum of losses {losses.net_pct.sum():+.1f}%  "
          f"|  net {window.net_pct.sum():+.1f}% per $100 lot")

    print("\n=== is there an uptrend being left behind? (trail exits only)")
    trail = window[window.kind == "trail"]
    print(f"{len(trail)} trailing exits. Peak reached {trail.peak_pct.mean():.2f}% on average, "
          f"kept {trail.net_pct.mean():.2f}%, left {trail.left_behind_pct.mean():.2f}% on the table.")
    for horizon in (30, 60, 120, 240, 1440):
        exits = trail.exit.to_numpy()
        valid = exits[exits + horizon < len(grid.CLOSE)]
        forward = grid.CLOSE[valid + horizon] / grid.CLOSE[valid] - 1
        print(f"  {horizon:>4} min after the trailing exit: price higher {100 * (forward > 0).mean():.0f}% of the time, "
              f"median {100 * np.median(forward):+.2f}%, mean {100 * forward.mean():+.2f}%")

    print("\n=== and after a stop-out?")
    stopped = window[window.kind == "stop"]
    for horizon in (60, 240, 1440):
        exits = stopped.exit.to_numpy()
        valid = exits[exits + horizon < len(grid.CLOSE)]
        forward = grid.CLOSE[valid + horizon] / grid.CLOSE[valid] - 1
        print(f"  {horizon:>4} min after the stop: price higher {100 * (forward > 0).mean():.0f}% of the time, "
              f"median {100 * np.median(forward):+.2f}%")
    trades.to_csv(grid.ROOT / "results" / "sol_live_trades.csv", index=False)


if __name__ == "__main__":
    main()
