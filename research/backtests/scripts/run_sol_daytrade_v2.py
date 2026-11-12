"""SOL intraday consolidation, with exits a day trader would actually use.

v1 failed for a reason it never tested: it forced every trade to reach +1.283% before the trailing stop armed,
while the zone it broke out of was only 0.1-2% wide. A 0.3% coil was being asked to travel four times its own
height before anything was locked in, against a stop of -0.75% or worse. Here the exit is sized to the move:

  target/arm:  +0.2, 0.3, 0.5, 0.75 % (trailing stop arms there, giving back 20 / 35 / 50 % of the gain)
  stop:        -0.2, -0.3, -0.5, -0.75, -1.0 %
  time exit:   60 minutes, 240 minutes, or none - a day trade should not be held for days
  zones:       1/3/5/10/15-minute charts, zone spanning 15 minutes to 4 hours, width 0.1 ... 0.75 %
  confirm:     0, 1, 3, 5 minutes after the break

$300 as 3 x $100 lots, both fee levels.
"""

from __future__ import annotations

import multiprocessing as mp
import time

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_consolidation_v4 as v4
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "SOLUSDT"
RESULT_DIR = grid.ROOT / "results" / "sol_daytrade_v2"
TIMEFRAMES = [1, 3, 5, 10, 15]
BARS = [6, 8, 10, 12, 16, 20, 24, 30, 40, 48]
SPAN = (15, 240)
ZONES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.75]
CONFIRM = [0, 1, 3, 5]
ACTIVATIONS = [0.2, 0.3, 0.5, 0.75]
GIVEBACKS = [20.0, 35.0, 50.0]
STOPS = [0.2, 0.3, 0.5, 0.75, 1.0]
HOLDS = [60, 240, 0]                    # 0 = no time exit
EXITS = [(activation, giveback, stop, hold)
         for hold in HOLDS for stop in STOPS for activation in ACTIVATIONS for giveback in GIVEBACKS]
COLS = len(EXITS)


def exits_for(entries):
    """Stop, trailing-stop or time exit for every exit column."""
    idx = np.full((len(entries), COLS), -1, dtype=np.int64)
    raw = np.full((len(entries), COLS), np.nan)
    code = np.zeros((len(entries), COLS), dtype=np.int8)
    last = len(grid.OPEN) - 1
    for row, entry in enumerate(entries):
        entry = int(entry)
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        arms = {a: research.first_hit(entry, fill * (1 + a / 100), True) for a in ACTIVATIONS}
        stops = {s: research.first_hit(entry, fill * (1 - s / 100), False) for s in STOPS}
        trails = {(a, g): (research.trail_exit(arms[a], fill, g) if arms[a] >= 0 else (-1, np.nan))
                  for a in ACTIVATIONS for g in GIVEBACKS}
        for column, (activation, giveback, stop, hold) in enumerate(EXITS):
            limit = min(entry + hold, last) if hold else last
            armed, stopped = arms[activation], stops[stop]
            trail_idx, trail_price = trails[(activation, giveback)]
            if stopped >= 0 and stopped <= limit and (armed < 0 or stopped <= armed):
                idx[row, column] = stopped
                raw[row, column] = min(fill * (1 - stop / 100), grid.OPEN[stopped])
                code[row, column] = 2
            elif armed >= 0 and armed <= limit and trail_idx >= 0 and trail_idx <= limit:
                idx[row, column], raw[row, column] = trail_idx, trail_price
                code[row, column] = 1
            else:                                              # still open when the clock runs out
                idx[row, column] = limit
                raw[row, column] = grid.OPEN[limit]
                code[row, column] = 3
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
    print(f"{len(configs)} entry configs, {sum(len(e) for _, e in configs):,} signals, {COLS} exit columns "
          f"({time.time() - started:.0f}s)", flush=True)
    unique = np.unique(np.concatenate([e for _, e in configs]))
    print(f"{len(unique):,} unique signals", flush=True)

    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(exits_for, np.array_split(unique, 240))
    research.TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    print(f"exit table {research.TABLE[0].shape} ({time.time() - started:.0f}s)", flush=True)

    tasks, keys, signal_counts = [], [], []
    for key, entries in configs:
        rows = np.searchsorted(unique, entries)
        entry_times = times[entries]
        masks = {name: (entry_times >= s) & (entry_times < e) for name, (s, e) in research.WINDOWS.items()}
        tasks.append((entries, rows, masks))
        keys.append(key)
        signal_counts.append(int(masks["full"].sum()))

    blocks = []
    for label, fee in (("usdt_10bps", 10.0), ("bnb_7.5bps", 7.5)):
        grid.FEE = fee / 10_000
        with context.Pool(8) as pool:
            results = pool.map(run_task, tasks, chunksize=4)
        print(f"simulated {len(tasks) * COLS:,} combinations at {label} ({time.time() - started:.0f}s)", flush=True)
        exit_frame = pd.DataFrame(EXITS, columns=["arm_pct", "giveback_pct", "stop_pct", "hold_minutes"])
        for (minutes, bars, zone, confirm), result, signals in zip(keys, results, signal_counts):
            block = exit_frame.copy()
            block["chart_minutes"], block["zone_bars"], block["zone_pct"] = minutes, bars, zone
            block["confirm_minutes"], block["fees"] = confirm, label
            block["zone_span_minutes"], block["full_signals"] = minutes * bars, signals
            for name, stats in result.items():
                for stat in research.STATS:
                    block[f"{name}_{stat}"] = stats[stat].astype(np.float32)
            blocks.append(block)
    board = pd.concat(blocks, ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} rows ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
