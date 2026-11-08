"""SOL consolidation, day-trading only: zones that form and break inside a single session.

The 24-hour zone that won the earlier search is not day trading - it produced 18 trades in two years. Here the
zone must be intraday and the point is to catch signals, not to be picky:

  chart:   1, 3, 5, 10, 15, 30 minutes
  zone:    6 ... 48 bars, but only where the zone spans 15 minutes to 8 hours
  width:   0.1 ... 2 % (tight, because an intraday zone is small)
  confirm: 0, 1, 2, 3, 5, 10, 15 minutes after the break
  stop:    -0.75 ... -3%
  trail:   giveback 12% -> +1.251%, up to 30% -> +1.315%

$300 as 3 x $100 lots, both fee levels. Each row also records how many signals the rule fired and how many the
account could actually take, so a rule that signals constantly but can never act shows up as such.
"""

from __future__ import annotations

import multiprocessing as mp
import time

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_fixed100_giveback_grid as gb
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "SOLUSDT"
RESULT_DIR = grid.ROOT / "results" / "sol_daytrade_v1"
TIMEFRAMES = [1, 3, 5, 10, 15, 30]
BARS = [6, 8, 10, 12, 16, 20, 24, 30, 40, 48]
SPAN = (15, 480)                                     # zone length in minutes: a quarter hour to eight hours
ZONES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0]
CONFIRM = [0, 1, 2, 3, 5, 10, 15]
STOPS = [0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
GIVEBACKS = [float(g) for g in range(12, 31, 2)]
PAIRS = [(round(gb.break_even_activation(g) + 1, 3), g) for g in GIVEBACKS]
EXITS = [(activation, giveback, stop) for stop in STOPS for activation, giveback in PAIRS]
COLS = len(EXITS)


def run_task(task):
    entries, rows, masks = task
    return {name: research.simulate(entries[mask], rows[mask]) for name, mask in masks.items()}


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    v4.PAIRS, v4.STOPS, v4.EXITS, v4.COLS = PAIRS, STOPS, EXITS, COLS
    research.COLS, research.LOT, research.LOTS, research.INITIAL = COLS, 100.0, 3, 300.0
    times = pd.DatetimeIndex(raw.open_time)

    configs = []
    for minutes in TIMEFRAMES:
        high, low, open_, close, last_minute = v4.bars_for(raw, minutes)
        for bars in BARS:
            if not SPAN[0] <= minutes * bars <= SPAN[1]:
                continue
            for zone in ZONES:
                for confirm in CONFIRM:
                    entries = v4.entries_for(high, low, close, last_minute, bars, zone, confirm, grid.CLOSE, len(raw))
                    if len(entries):
                        configs.append(((minutes, bars, zone, confirm), entries))
    print(f"{len(configs)} entry configs, {sum(len(e) for _, e in configs):,} signals ({time.time() - started:.0f}s)",
          flush=True)
    unique = np.unique(np.concatenate([e for _, e in configs]))
    print(f"{len(unique):,} unique signals", flush=True)

    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(v4.exits_for, np.array_split(unique, 240))
    research.TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    print(f"exit table {research.TABLE[0].shape} ({time.time() - started:.0f}s)", flush=True)

    tasks, keys, signal_counts = [], [], []
    for key, entries in configs:
        rows = np.searchsorted(unique, entries)
        entry_times = times[entries]
        masks = {name: (entry_times >= s) & (entry_times < e) for name, (s, e) in research.WINDOWS.items()}
        tasks.append((entries, rows, masks))
        keys.append(key)
        signal_counts.append({name: int(mask.sum()) for name, mask in masks.items()})

    blocks = []
    for label, fee in (("usdt_10bps", 10.0), ("bnb_7.5bps", 7.5)):
        grid.FEE = fee / 10_000
        with context.Pool(8) as pool:
            results = pool.map(run_task, tasks, chunksize=4)
        print(f"simulated {len(tasks) * COLS:,} combinations at {label} ({time.time() - started:.0f}s)", flush=True)
        exit_frame = pd.DataFrame(EXITS, columns=["trail_start_pct", "giveback_pct", "stop_pct"])
        for (minutes, bars, zone, confirm), result, signals in zip(keys, results, signal_counts):
            block = exit_frame.copy()
            block["chart_minutes"], block["zone_bars"], block["zone_pct"] = minutes, bars, zone
            block["confirm_minutes"], block["fees"] = confirm, label
            block["zone_span_minutes"] = minutes * bars
            block["full_signals"] = signals["full"]
            for name, stats in result.items():
                for stat in research.STATS:
                    block[f"{name}_{stat}"] = stats[stat].astype(np.float32)
            blocks.append(block)
    board = pd.concat(blocks, ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} rows ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
