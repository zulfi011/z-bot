"""SOL only: consolidation breakout on 1/3/5/10/15/30-minute charts, day-trading settings.

Entry
  - on a TF-minute chart, the last K bars form a zone: highest high / lowest low - 1 <= zone size
  - a bar closes above the zone top (leaves upward). A close below the zone bottom is ignored.
  - confirmation wait: 0, 1, 3, 5, 10, 15 or 30 minutes after that close. The buy only happens if the price is
    still above the zone top when the wait ends (a fall back into the zone during the wait cancels it).
  - buy at the next minute's open.

Exit
  - stop −1 … −4% from the fill, for a break that fails before the trailing stop arms
  - trailing stop armed once the trade is up: giveback 12% → start +1.251%, rising to 30% → +1.315%

Costs: 2 bps slippage per side; results at 10 bps (USDT fees) and at 7.5 bps (fees paid in BNB).
Account: $300 as 3 × $100 lots, at most 3 open, no time exit.
"""

from __future__ import annotations

import multiprocessing as mp
import time

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_fixed100_giveback_grid as gb
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "SOLUSDT"
RESULT_DIR = grid.ROOT / "results" / "sol_consolidation_v4"
TIMEFRAMES = [1, 3, 5, 10, 15, 30]          # the chart the zone is drawn on
BARS = [10, 20, 40]                          # how many bars the zone must hold
ZONES = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0]      # zone height, %
CONFIRM = [0, 1, 3, 5, 10, 15, 30]           # minutes to confirm the break before buying
STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
GIVEBACKS = [float(g) for g in range(12, 31, 2)]
PAIRS = [(round(gb.break_even_activation(g) + 1, 3), g) for g in GIVEBACKS]
EXITS = [(activation, giveback, stop) for stop in STOPS for activation, giveback in PAIRS]
COLS = len(EXITS)


def bars_for(raw: pd.DataFrame, minutes: int):
    """TF-minute bars plus the 1-minute index each bar closes on."""
    if minutes == 1:
        return (raw.high.to_numpy(float), raw.low.to_numpy(float), raw.open.to_numpy(float),
                raw.close.to_numpy(float), np.arange(len(raw)))
    bucket = np.arange(len(raw)) // minutes
    frame = pd.DataFrame({"bucket": bucket, "high": raw.high.to_numpy(float), "low": raw.low.to_numpy(float),
                          "open": raw.open.to_numpy(float), "close": raw.close.to_numpy(float),
                          "index": np.arange(len(raw))})
    grouped = frame.groupby("bucket").agg(high=("high", "max"), low=("low", "min"), open=("open", "first"),
                                          close=("close", "last"), index=("index", "last"), count=("index", "size"))
    grouped = grouped[grouped["count"] == minutes]                     # only whole bars
    return (grouped.high.to_numpy(), grouped.low.to_numpy(), grouped.open.to_numpy(), grouped.close.to_numpy(),
            grouped["index"].to_numpy())


def entries_for(high, low, close, last_minute, bars, zone, confirm, minute_close, minute_count):
    """Entry indices (1-minute) for one chart / zone / confirmation-wait combination."""
    top = pd.Series(high).rolling(bars).max().to_numpy()
    bottom = pd.Series(low).rolling(bars).min().to_numpy()
    zone_top = np.r_[np.nan, top[:-1]]                                  # the zone as it stood before this bar
    zone_bottom = np.r_[np.nan, bottom[:-1]]
    quiet = (zone_top / zone_bottom - 1) <= zone / 100
    broke = quiet & (close > zone_top)
    first = broke & ~np.r_[False, broke[:-1]]                           # first break out of each quiet stretch
    where = np.flatnonzero(first)
    breakout_minute = last_minute[where]
    check = breakout_minute + confirm                                    # still above the zone when the wait ends?
    valid = check < minute_count - 1
    where, check = where[valid], check[valid]
    held = minute_close[check] > zone_top[where]
    return (check[held] + 1).astype(np.int64)                            # buy at the next minute's open


def exits_for(entries):
    """Stop and trailing-stop outcome for every exit combination."""
    idx = np.full((len(entries), COLS), -1, dtype=np.int64)
    raw = np.full((len(entries), COLS), np.nan)
    code = np.zeros((len(entries), COLS), dtype=np.int8)
    for row, entry in enumerate(entries):
        entry = int(entry)
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        arms = {activation: research.first_hit(entry, fill * (1 + activation / 100), True) for activation, _ in PAIRS}
        horizon = None if min(arms.values()) < 0 else max(arms.values())
        stops = {stop: research.first_hit(entry, fill * (1 - stop / 100), False, horizon) for stop in STOPS}
        trails = {(a, g): (research.trail_exit(arms[a], fill, g) if arms[a] >= 0 else (-1, np.nan)) for a, g in PAIRS}
        for column, (activation, giveback, stop) in enumerate(EXITS):
            armed, stopped = arms[activation], stops[stop]
            if stopped >= 0 and (armed < 0 or stopped <= armed):
                idx[row, column] = stopped
                raw[row, column] = min(fill * (1 - stop / 100), grid.OPEN[stopped])
                code[row, column] = 2
            elif armed >= 0 and trails[(activation, giveback)][0] >= 0:
                idx[row, column], raw[row, column] = trails[(activation, giveback)]
                code[row, column] = 1
    return idx, raw, code


def run_task(task):
    entries, rows, masks = task
    return {name: research.simulate(entries[mask], rows[mask]) for name, mask in masks.items()}


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    research.COLS = COLS
    times = pd.DatetimeIndex(raw.open_time)
    minute_close, minute_count = grid.CLOSE, len(raw)

    configs = []
    for minutes in TIMEFRAMES:
        high, low, open_, close, last_minute = bars_for(raw, minutes)
        for bars in BARS:
            for zone in ZONES:
                for confirm in CONFIRM:
                    entries = entries_for(high, low, close, last_minute, bars, zone, confirm, minute_close, minute_count)
                    if len(entries):
                        configs.append(((minutes, bars, zone, confirm), entries))
    print(f"{len(configs)} entry configs, {sum(len(e) for _, e in configs):,} entries ({time.time() - started:.0f}s)",
          flush=True)
    unique = np.unique(np.concatenate([e for _, e in configs]))
    print(f"{len(unique):,} unique entries", flush=True)

    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(exits_for, np.array_split(unique, 200))
    research.TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    print(f"exit table {research.TABLE[0].shape} ({time.time() - started:.0f}s)", flush=True)

    tasks, keys = [], []
    for key, entries in configs:
        rows = np.searchsorted(unique, entries)
        entry_times = times[entries]
        masks = {name: (entry_times >= s) & (entry_times < e) for name, (s, e) in research.WINDOWS.items()}
        tasks.append((entries, rows, masks))
        keys.append(key)

    blocks = []
    for label, fee in (("usdt_10bps", 10.0), ("bnb_7.5bps", 7.5)):
        grid.FEE = fee / 10_000
        with context.Pool(8) as pool:
            results = pool.map(run_task, tasks, chunksize=4)
        print(f"simulated {len(tasks) * COLS:,} combinations at {label} ({time.time() - started:.0f}s)", flush=True)
        exit_frame = pd.DataFrame(EXITS, columns=["trail_start_pct", "giveback_pct", "stop_pct"])
        for (minutes, bars, zone, confirm), result in zip(keys, results):
            block = exit_frame.copy()
            block["chart_minutes"], block["zone_bars"], block["zone_pct"] = minutes, bars, zone
            block["confirm_minutes"], block["fees"] = confirm, label
            block["zone_span_minutes"] = minutes * bars
            for name, stats in result.items():
                for stat in research.STATS:
                    block[f"{name}_{stat}"] = stats[stat].astype(np.float32)
            blocks.append(block)
    board = pd.concat(blocks, ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} rows ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
