"""ETH: the full SOL procedure in one grid, plus walk-forward windows.

Entry: 1/3/5m candles × 1–15 day completed-close average × ±0.1…0.5% zone, from
below + bullish confirmation, avoid strong bearish. Exits: stop −0.5…−4%,
giveback 10…30% (step 2) with the break-even trail start (+0.245…+0.315%) or
break-even + 1% (+1.245…+1.315%); +1% starts also try a break-even stop after
+0.5% / +0.75%. Filters: trend none / above 30-day / above 30-day ≤ +10%, and
all hours / skip 06–12 UTC entries. $300, full $100 lots, at most 3 open, no
time exit, 10 bps fee + 2 bps slippage.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import time

import numpy as np
import pandas as pd

import run_sol_fixed100_giveback_grid as gb
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

SYMBOL = "ETHUSDT"
RESULT_DIR = grid.ROOT / "results" / "eth_full_research_v2"
TIMEFRAMES = [1, 3, 5]
AVERAGE_DAYS = list(range(1, 16))
ZONES = [0.1, 0.2, 0.3, 0.4, 0.5]
STOPS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
GIVEBACKS = [float(g) for g in range(10, 31, 2)]
BE_LEVEL = round(gb.BREAK_EVEN * 100, 4)
TRENDS = ["none", "above_30d", "above_30d_max10"]
TIME_FILTERS = [False, True]
LOT, LOTS, INITIAL = 100.0, 3, 300.0
NEVER = np.iinfo(np.int64).max
UTC = "UTC"

# Exit columns: (mode, activation %, giveback %, break-even trigger, stop %).
PAIRS = [("break_even", gb.break_even_activation(g), g) for g in GIVEBACKS] + \
        [("plus_1pct", round(gb.break_even_activation(g) + 1, 3), g) for g in GIVEBACKS]
EXITS = [(mode, act, g, be, stop) for stop in STOPS for mode, act, g in PAIRS
         for be in ([None] if mode == "break_even" else [None, 0.5, 0.75])]
COLS = len(EXITS)
T = lambda value: pd.Timestamp(value, tz=UTC)  # noqa: E731
WINDOWS = {"full": (T("2024-10-01"), T("2026-08-01")), "earlier": (T("2024-10-01"), T("2025-09-01")),
           "later": (T("2025-09-01"), T("2026-08-01")), "unseen": (T("2026-08-01"), T("2026-09-11"))}
TESTS = [("2025-04-01", "2025-07-01"), ("2025-07-01", "2025-10-01"), ("2025-10-01", "2026-01-01"),
         ("2026-01-01", "2026-04-01"), ("2026-04-01", "2026-07-01"), ("2026-07-01", "2026-08-01")]
for i, (start, end) in enumerate(TESTS):
    WINDOWS[f"wf{i}_test"] = (T(start), T(end))
    WINDOWS[f"wf{i}_train"] = (T(start) - pd.DateOffset(months=6), T(start))
STATS = ["trades", "wins", "profit", "gross_win", "gross_loss", "dd", "trail", "stop", "breakeven"]

TABLE = None      # (idx, raw, code) per unique entry, set before forking


def first_hit(start, level, above, until=None):
    series = grid.HIGH if above else grid.LOW
    end_all = len(series) if until is None else min(len(series), until + 1)
    position = start
    while position < end_all:
        end = min(position + 2048, end_all)
        chunk = series[position:end]
        hits = np.flatnonzero(chunk >= level if above else chunk <= level)
        if len(hits):
            return position + int(hits[0])
        position = end
    return -1


def trail_exit(activation, fill, giveback):
    peak, position, count, keep = grid.HIGH[activation], activation + 1, len(grid.LOW), 1 - giveback / 100
    while position < count:
        end = min(position + 2048, count)
        chunk_high = grid.HIGH[position:end]
        prior = np.maximum.accumulate(np.r_[peak, chunk_high[:-1]])
        trails = fill + (prior - fill) * keep
        hits = np.flatnonzero(grid.LOW[position:end] <= trails)
        if len(hits):
            index = position + int(hits[0])
            return index, min(float(trails[hits[0]]), grid.OPEN[index])
        peak = max(peak, float(chunk_high.max()))
        position = end
    return -1, np.nan


def exits_for(entries):
    idx = np.full((len(entries), COLS), -1, dtype=np.int64)
    raw = np.full((len(entries), COLS), np.nan)
    code = np.zeros((len(entries), COLS), dtype=np.int8)
    for row, entry in enumerate(entries):
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        acts = {act: first_hit(entry, fill * (1 + act / 100), True) for _, act, _ in PAIRS}
        horizon = None if min(acts.values()) < 0 else max(acts.values())
        stops = {s: first_hit(entry, fill * (1 - s / 100), False, horizon) for s in STOPS}
        be_price = fill * (1 + BE_LEVEL / 100)
        triggers = {be: first_hit(entry, fill * (1 + be / 100), True, horizon) for be in (0.5, 0.75)}
        be_hits = {be: (first_hit(t + 1, be_price, False, horizon) if t >= 0 else -1) for be, t in triggers.items()}
        trails = {(act, g): (trail_exit(acts[act], fill, g) if acts[act] >= 0 else (-1, np.nan)) for _, act, g in PAIRS}
        for column, (_, act, g, be, stop) in enumerate(EXITS):
            t_act, t_stop = acts[act], stops[stop]
            armed = be is not None and triggers[be] >= 0 and (t_act < 0 or triggers[be] < t_act)
            if t_stop >= 0 and (t_act < 0 or t_stop <= t_act) and (not armed or t_stop <= triggers[be]):
                idx[row, column], raw[row, column] = t_stop, min(fill * (1 - stop / 100), grid.OPEN[t_stop])
                code[row, column] = 2
            elif armed and be_hits[be] >= 0 and (t_act < 0 or be_hits[be] <= t_act):
                idx[row, column], raw[row, column], code[row, column] = be_hits[be], min(be_price, grid.OPEN[be_hits[be]]), 5
            elif t_act >= 0 and trails[(act, g)][0] >= 0:
                idx[row, column], raw[row, column] = trails[(act, g)]
                code[row, column] = 1
    return idx, raw, code


def simulate(entries, rows):
    """All exit columns at once: $300, full $100 lots, ≤ 3 open, 10/2 bps."""
    idx_table, raw_table, code_table = TABLE
    cash = np.full(COLS, INITIAL)
    active = np.zeros((COLS, LOTS), dtype=bool)
    exits = np.full((COLS, LOTS), NEVER, dtype=np.int64)
    qty = np.zeros((COLS, LOTS))
    unit = np.zeros((COLS, LOTS))
    kind = np.zeros((COLS, LOTS), dtype=np.int8)
    out = {name: np.zeros(COLS) for name in STATS}
    peak = np.full(COLS, INITIAL)
    columns = np.arange(COLS)

    def close(mask):
        nonlocal cash
        proceeds = np.where(mask, qty * unit, 0.0)
        pnl = np.where(mask, proceeds - LOT, 0.0)
        cash = cash + proceeds.sum(1)
        out["trades"] += mask.sum(1)
        out["wins"] += (mask & (pnl > 0)).sum(1)
        out["gross_win"] += np.where(pnl > 0, pnl, 0).sum(1)
        out["gross_loss"] -= np.where(pnl < 0, pnl, 0).sum(1)
        out["trail"] += (mask & (kind == 1)).sum(1)
        out["stop"] += (mask & (kind == 2)).sum(1)
        out["breakeven"] += (mask & (kind == 5)).sum(1)
        active[mask] = False

    for entry, row in zip(entries, rows):
        close(active & (exits < entry))
        marked = cash + (qty * active).sum(1) * grid.OPEN[entry]
        np.maximum(peak, marked, out=peak)
        out["dd"] = np.minimum(out["dd"], (marked / peak - 1) * 100)
        can = (active.sum(1) < LOTS) & (cash >= LOT)
        if not can.any():
            continue
        slot = np.argmin(active, axis=1)
        target = columns[can], slot[can]
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        e_idx = idx_table[row]
        qty[target] = LOT / (fill * (1 + grid.FEE))
        exits[target] = np.where(e_idx < 0, NEVER, e_idx)[can]
        unit[target] = (raw_table[row] * (1 - grid.SLIP) * (1 - grid.FEE))[can]
        kind[target] = code_table[row][can]
        active[target] = True
        cash = cash - np.where(can, LOT, 0.0)
    close(active & (exits < NEVER))
    final = cash + (qty * active).sum(1) * grid.CLOSE[-1]
    out["profit"] = final - INITIAL
    out["dd"] = np.minimum(out["dd"], (final / np.maximum(peak, final) - 1) * 100)
    return out


def run_task(task):
    entries, rows, masks = task
    return {name: simulate(entries[mask], rows[mask]) for name, mask in masks.items()}


def features(signals, minutes, daily, times):
    entry = signals.entry_index.to_numpy()
    confirm_day = times[entry - minutes].floor("D")
    a30 = np.array([daily.get(d, (np.nan,) * 3)[2] for d in confirm_day])
    stretch = grid.CLOSE[entry - 1] / a30 - 1
    hour = times[entry].hour
    return {"none": np.ones(len(entry), bool), "above_30d": stretch > 0, "above_30d_max10": (stretch > 0) & (stretch <= 0.10),
            "morning": (hour >= 6) & (hour < 12)}


def main() -> None:
    global TABLE
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    gaps = raw.open_time.diff().iloc[1:] != pd.Timedelta(minutes=1)
    if gaps.any():
        raise ValueError(f"{SYMBOL} data has {int(gaps.sum())} gaps")
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in replay.daily_averages(raw).items()}
    extra = {n: {d: float(v) if v is not None else np.nan for d, v in replay.daily_average_n(raw, n).items()} for n in AVERAGE_DAYS}
    configs = []
    for minutes in TIMEFRAMES:
        frame = grid.signal_frame(raw, daily, minutes)
        days = frame["open_time"].floor("D")
        for n in AVERAGE_DAYS:
            view = {**frame, "signal": np.array([extra[n].get(d, np.nan) for d in days])}
            for zone in ZONES:
                config = {"signal_minutes": minutes, "average_days": "signal",
                          "zone_pct": zone, "approach": "from_below", "market_filter": "avoid_strong_bearish"}
                signals = grid.fast_signals(view, config)
                signals = signals[signals.entry_index < len(raw)].reset_index(drop=True)
                configs.append(((minutes, n, zone), signals, features(signals, minutes, daily, times)))
    unique = np.unique(np.concatenate([s.entry_index.to_numpy() for _, s, _ in configs]))
    print(f"{len(configs)} entry configs, {sum(len(s) for _, s, _ in configs):,} signals, {len(unique):,} entries "
          f"({time.time() - started:.0f}s)", flush=True)
    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(exits_for, np.array_split(unique, 160))
    TABLE = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    print(f"exit table {TABLE[0].shape} ({time.time() - started:.0f}s)", flush=True)

    tasks, keys = [], []
    for key, signals, feats in configs:
        entries = signals.entry_index.to_numpy()
        rows = np.searchsorted(unique, entries)
        entry_times = times[entries]
        for trend in TRENDS:
            for skip in TIME_FILTERS:
                keep = feats[trend] & ~(feats["morning"] & skip)
                masks = {name: keep & (signals.touch_time >= s).to_numpy() & (entry_times < e)
                         for name, (s, e) in WINDOWS.items()}
                tasks.append((entries, rows, masks))
                keys.append((*key, trend, skip))
    with context.Pool(8) as pool:
        results = pool.map(run_task, tasks, chunksize=6)
    print(f"simulated {len(tasks) * COLS:,} combinations × {len(WINDOWS)} windows ({time.time() - started:.0f}s)", flush=True)

    exit_frame = pd.DataFrame(EXITS, columns=["trail_mode", "activation_pct", "giveback_pct", "be_trigger", "stop_pct"])
    blocks = []
    for (minutes, n, zone, trend, skip), result in zip(keys, results):
        block = exit_frame.copy()
        block["signal_minutes"], block["average_days"], block["zone_pct"] = minutes, n, zone
        block["trend"], block["skip_06_12"] = trend, skip
        for window, stats in result.items():
            for name in STATS:
                block[f"{window}_{name}"] = stats[name].astype(np.float32)
        blocks.append(block)
    board = pd.concat(blocks, ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} rows ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
