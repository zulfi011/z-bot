"""SOL consolidation breakout v3: quiet measured against SOL's own recent volatility, exits built for breakouts.

v1/v2 found the pattern but not a tradeable version: a fixed % band means different things in calm and wild weeks,
and the exits were borrowed from the dip strategy (trailing only arms at +1.25%, gives back up to 30%).

Entry
  - the last N minutes form a range whose height sits in the quietest Q% of the ranges seen over the previous 30
    days (thresholds come only from earlier days, so nothing is known in advance)
  - the next 1-minute candle closes above the range top, by a margin, is green, and closes in the top third of its
    own bar; optionally its volume must beat the last hour's average
  - optional: only above the 30-day average; optional: skip 06–12 UTC
  - buy at the next minute's open

Exit (each combination tried)
  - stop at the range low, or 0.2% below it
  - target at 1x / 1.5x / 2x / 3x the range height above the fill, or none
  - trailing stop from break-even giving back 15% or 30% of the peak, or none
  - give-up timer: leave after 30 / 60 / 120 minutes if the trade has not reached break-even, or never

$300 as 3 x $100 lots, at most 3 open, 10 bps fee + 2 bps slippage, exactly as every other test in this project.
"""

from __future__ import annotations

import multiprocessing as mp
import time
import zipfile

import numpy as np
import pandas as pd

import run_eth_full_research as research
import run_sol_fixed100_giveback_grid as gb
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "SOLUSDT"
RESULT_DIR = grid.ROOT / "results" / "sol_consolidation_v3"
WINDOWS_MIN = [30, 60, 120, 240]          # how long the range must hold
QUIETEST_PCT = [20, 30, 40]               # how quiet, against the last 30 days of ranges
MARGINS = [0.0, 0.1]                      # % the close must clear the range top by
VOLUME_MULTS = [0.0, 1.5]                 # 0 = no volume filter; else volume vs the last hour's average
STRENGTH = [0.0, 2 / 3]                   # where the close must sit inside the breakout candle
TRENDS = ["none", "above_30d"]
TIME_FILTERS = [False, True]
LOOKBACK_DAYS = 30

STOP_BUFFERS = [0.0, 0.2]                 # % below the range low
TARGETS = [None, 1.0, 1.5, 2.0, 3.0]      # multiples of the range height
TRAILS = [None, 15.0, 30.0]               # giveback %, armed at break-even
TIMERS = [None, 30, 60, 120]              # minutes to reach break-even before giving up
EXITS = [(buffer, target, trail, timer) for buffer in STOP_BUFFERS for target in TARGETS
         for trail in TRAILS for timer in TIMERS]
COLS = len(EXITS)
BE = gb.BREAK_EVEN * 100                  # % move that covers a round trip's costs
ENTRIES = None                            # (entry index, stop price, target height) set before forking


def load_with_volume(symbol: str) -> pd.DataFrame:
    """Prices and volume for the history plus the unseen weeks (the shared loader skips volume)."""
    frame = pd.read_parquet(replay.RAW_DIR / symbol / f"{symbol}_1m.parquet",
                            columns=["open_time", "open", "high", "low", "close", "volume"])
    parts = []
    for path in sorted(replay.HOLDOUT_DIR.glob(f"{symbol}-1m-*.zip")):
        with zipfile.ZipFile(path) as archive, archive.open(archive.namelist()[0]) as handle:
            part = pd.read_csv(handle, header=None, usecols=range(6))
        parts.append(part[part[0].astype(str).str.isdigit()])
    extra = pd.concat(parts)
    extra.columns = ["open_time", "open", "high", "low", "close", "volume"]
    stamps = extra.open_time.astype("int64")
    # Binance spot archives switched from milliseconds to microseconds in 2025.
    extra["open_time"] = pd.to_datetime(np.where(stamps > 10**14, stamps, stamps * 1000), unit="us", utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        extra[column] = extra[column].astype(float)
    return (pd.concat([frame, extra]).drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True))


def quiet_ranges(high, low, window, days, quietest_pct):
    """Range height of the N minutes before each candle, and whether it is among the quietest of the last 30 days."""
    top = pd.Series(high).rolling(window).max().to_numpy()
    bottom = pd.Series(low).rolling(window).min().to_numpy()
    height = np.r_[np.nan, (top[:-1] / bottom[:-1] - 1) * 100]
    top_prev, bottom_prev = np.r_[np.nan, top[:-1]], np.r_[np.nan, bottom[:-1]]
    threshold = np.full(len(days), np.nan)
    order = np.unique(days)
    for position, day in enumerate(order):
        if position < LOOKBACK_DAYS:
            continue
        window_days = order[position - LOOKBACK_DAYS:position]
        sample = height[np.isin(days, window_days)]
        sample = sample[~np.isnan(sample)]
        if len(sample):
            threshold[days == day] = np.percentile(sample, quietest_pct)
    return top_prev, bottom_prev, height, height <= threshold


def exits_for(chunk):
    """Exit index, price and reason for one block of entries, for every exit combination."""
    idx = np.full((len(chunk), COLS), -1, dtype=np.int64)
    raw = np.full((len(chunk), COLS), np.nan)
    code = np.zeros((len(chunk), COLS), dtype=np.int8)
    for row, (entry, stop_low, height) in enumerate(chunk):
        entry = int(entry)
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        stops = {buffer: research.first_hit(entry, stop_low * (1 - buffer / 100), False) for buffer in STOP_BUFFERS}
        targets = {t: research.first_hit(entry, fill + t * height, True) for t in TARGETS if t is not None}
        break_even = research.first_hit(entry, fill * (1 + BE / 100), True)
        trails = {g: (research.trail_exit(break_even, fill, g) if break_even >= 0 else (-1, np.nan)) for g in TRAILS if g}
        for column, (buffer, target, trail, timer) in enumerate(EXITS):
            options = [(stops[buffer], stop_low * (1 - buffer / 100), 2)]
            if target is not None and targets[target] >= 0:
                options.append((targets[target], fill + target * height, 3))
            if trail is not None and trails[trail][0] >= 0:
                options.append((trails[trail][0], trails[trail][1], 1))
            if timer is not None:
                # Give up at the timer unless break-even was reached before it.
                if break_even < 0 or break_even > entry + timer:
                    options.append((min(entry + timer, len(grid.OPEN) - 1), np.nan, 4))
            options = [(when, price, reason) for when, price, reason in options if when >= 0]
            if not options:
                continue
            when, price, reason = min(options, key=lambda item: item[0])
            idx[row, column] = when
            code[row, column] = reason
            if reason == 2:
                raw[row, column] = min(price, grid.OPEN[when])       # a gap fills worse than the stop
            elif reason == 3:
                raw[row, column] = max(price, grid.OPEN[when])       # a gap fills better than the target
            elif reason == 1:
                raw[row, column] = min(price, grid.OPEN[when])
            else:
                raw[row, column] = grid.CLOSE[when]                  # timer: out at that minute's close
    return idx, raw, code


def run_task(task):
    entries, rows, masks = task
    return {name: research.simulate(entries[mask], rows[mask]) for name, mask in masks.items()}


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_with_volume(SYMBOL)
    raw = raw[raw.open_time < research.T("2026-09-11")].reset_index(drop=True)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    volume = raw.volume.to_numpy(float)
    hour_volume = pd.Series(volume).rolling(60).mean().shift(1).to_numpy()
    times = pd.DatetimeIndex(raw.open_time)
    days = times.floor("D").asi8
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals)
             for d, vals in replay.daily_averages(raw).items()}
    body = grid.CLOSE - grid.OPEN
    span = np.where(grid.HIGH > grid.LOW, grid.HIGH - grid.LOW, np.nan)
    close_position = (grid.CLOSE - grid.LOW) / span                   # 1 = closed at the high of the bar

    configs = []
    for window in WINDOWS_MIN:
        for quietest in QUIETEST_PCT:
            top_prev, bottom_prev, height, quiet = quiet_ranges(grid.HIGH, grid.LOW, window, days, quietest)
            for margin in MARGINS:
                broke = quiet & (grid.CLOSE > top_prev * (1 + margin / 100)) & (body > 0)
                for strength in STRENGTH:
                    strong = broke & (np.nan_to_num(close_position, nan=0.0) >= strength)
                    for mult in VOLUME_MULTS:
                        keep = strong if mult == 0 else strong & (volume >= mult * np.nan_to_num(hour_volume))
                        first = keep & ~np.r_[False, keep[:-1]]
                        index = np.flatnonzero(first)
                        index = index[index < len(grid.OPEN) - 2]
                        entries = index + 1                              # fill at the next minute's open
                        # entry index, the stop level (range low) and the range height in price
                        block = np.column_stack([entries, bottom_prev[index], top_prev[index] - bottom_prev[index]])
                        configs.append(((window, quietest, margin, strength, mult), block))
    print(f"{len(configs)} entry configs, {sum(len(b) for _, b in configs):,} breakouts ({time.time() - started:.0f}s)",
          flush=True)

    all_entries = np.concatenate([b for _, b in configs])
    unique_rows, inverse = np.unique(all_entries, axis=0, return_inverse=True)
    print(f"{len(unique_rows):,} unique entry+level combinations", flush=True)
    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(exits_for, np.array_split(unique_rows, 200))
    research.TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    research.COLS = COLS
    print(f"exit table {research.TABLE[0].shape} ({time.time() - started:.0f}s)", flush=True)

    lookup = {tuple(row): i for i, row in enumerate(unique_rows)}
    tasks, keys = [], []
    for key, block in configs:
        entries = block[:, 0].astype(np.int64)
        rows = np.array([lookup[tuple(row)] for row in block], dtype=np.int64)
        feats = research.features(pd.DataFrame({"entry_index": entries}), 1, daily, times)
        entry_times = times[entries]
        for trend in TRENDS:
            for skip in TIME_FILTERS:
                keep = feats[trend] & ~(feats["morning"] & skip)
                masks = {name: keep & (entry_times >= s) & (entry_times < e)
                         for name, (s, e) in research.WINDOWS.items()}
                tasks.append((entries, rows, masks))
                keys.append((*key, trend, skip))
    with context.Pool(8) as pool:
        results = pool.map(run_task, tasks, chunksize=4)
    print(f"simulated {len(tasks) * COLS:,} combinations × {len(research.WINDOWS)} windows "
          f"({time.time() - started:.0f}s)", flush=True)

    exit_frame = pd.DataFrame(EXITS, columns=["stop_buffer_pct", "target_x_range", "trail_giveback_pct", "timer_minutes"])
    blocks = []
    for (window, quietest, margin, strength, mult, trend, skip), result in zip(keys, results):
        block = exit_frame.copy()
        block["window_minutes"], block["quietest_pct"], block["margin_pct"] = window, quietest, margin
        block["close_strength"], block["volume_mult"], block["trend"], block["skip_06_12"] = strength, mult, trend, skip
        for name, stats in result.items():
            for stat in research.STATS:
                block[f"{name}_{stat}"] = stats[stat].astype(np.float32)
        blocks.append(block)
    board = pd.concat(blocks, ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} rows ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
