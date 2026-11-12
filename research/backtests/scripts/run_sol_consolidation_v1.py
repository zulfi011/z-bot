"""SOL consolidation breakout: no averages. Buy when a quiet range breaks upward.

Entry: the last N minutes stay inside a band of X% (highest high / lowest low - 1 <= X). The next 1-minute candle
closes above the band top AND is green (close > open) -> buy at the following minute's open. A downward break is
ignored. Only the first breakout of each quiet stretch counts.

  band X:   0.5, 1, 1.5, 2, 2.5, 3 %      window N: 1, 3, 5, 10, 15, 30 minutes

Exits, costs and account are exactly the ones used for every coin in this project: stop -0.5...-4%, trailing start
at break-even or break-even + 1% giving back 10...30%, optional break-even stop, no time exit, $300 as 3 x $100
lots, at most 3 open, 10 bps fee + 2 bps slippage. Filters: trend none / above 30-day average, all hours / skip
06-12 UTC.
"""

from __future__ import annotations

import multiprocessing as mp
import time

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "SOLUSDT"
RESULT_DIR = grid.ROOT / "results" / "sol_consolidation_v1"
BANDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
MINUTES = [1, 3, 5, 10, 15, 30]
TRENDS = ["none", "above_30d"]
TIME_FILTERS = [False, True]


def breakouts(high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray, band: float, window: int):
    """Entry indices: the minute after a green candle closes above a quiet range."""
    top = pd.Series(high).rolling(window).max().to_numpy()      # range of the N minutes before this candle
    bottom = pd.Series(low).rolling(window).min().to_numpy()
    quiet = np.zeros(len(close), bool)
    quiet[1:] = (top[:-1] / bottom[:-1] - 1) <= band / 100
    ceiling = np.r_[np.nan, top[:-1]]
    broke = quiet & (close > ceiling) & (close > open_)
    first = broke & ~np.r_[False, broke[:-1]]                   # only the first breakout of each quiet stretch
    entries = np.flatnonzero(first) + 1                          # fill at the next minute's open
    return entries[entries < len(close) - 1]


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals)
             for d, vals in replay.daily_averages(raw).items()}

    configs = []
    for band in BANDS:
        for window in MINUTES:
            entries = breakouts(grid.HIGH, grid.LOW, grid.OPEN, grid.CLOSE, band, window)
            feats = research.features(pd.DataFrame({"entry_index": entries}), 1, daily, times)
            configs.append(((band, window), entries, feats))
            print(f"  band {band}% window {window}m: {len(entries):,} breakouts", flush=True)
    unique = np.unique(np.concatenate([e for _, e, _ in configs]))
    print(f"{len(configs)} entry configs, {sum(len(e) for _, e, _ in configs):,} breakouts, "
          f"{len(unique):,} unique entries ({time.time() - started:.0f}s)", flush=True)

    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(research.exits_for, np.array_split(unique, 200))
    research.TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    print(f"exit table {research.TABLE[0].shape} ({time.time() - started:.0f}s)", flush=True)

    tasks, keys = [], []
    for key, entries, feats in configs:
        rows = np.searchsorted(unique, entries)
        entry_times = times[entries]
        for trend in TRENDS:
            for skip in TIME_FILTERS:
                keep = feats[trend] & ~(feats["morning"] & skip)
                masks = {name: keep & (entry_times >= s) & (entry_times < e)
                         for name, (s, e) in research.WINDOWS.items()}
                tasks.append((entries, rows, masks))
                keys.append((*key, trend, skip))
    with context.Pool(8) as pool:
        results = pool.map(research.run_task, tasks, chunksize=4)
    print(f"simulated {len(tasks) * research.COLS:,} combinations × {len(research.WINDOWS)} windows "
          f"({time.time() - started:.0f}s)", flush=True)

    exit_frame = pd.DataFrame(research.EXITS, columns=["trail_mode", "activation_pct", "giveback_pct", "be_trigger", "stop_pct"])
    blocks = []
    for (band, window, trend, skip), result in zip(keys, results):
        block = exit_frame.copy()
        block["band_pct"], block["window_minutes"], block["trend"], block["skip_06_12"] = band, window, trend, skip
        for name, stats in result.items():
            for stat in research.STATS:
                block[f"{name}_{stat}"] = stats[stat].astype(np.float32)
        blocks.append(block)
    board = pd.concat(blocks, ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} rows ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
