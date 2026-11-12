"""Every combination of Stage 3-deployable SOL rules: entry, exits, hold limit, sizing.

Fast vectorised re-implementation of the Stage 3 rules, checked against the
exact replay (`stage3_replay`) for signals and for the live baseline. The
candidate is selected on the earlier period only; later and the unseen
holdout are used once, to judge it.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import time
from pathlib import Path

import numpy as np
import pandas as pd

import stage3_replay as replay

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ID = "sol_stage3_space_grid_v1"
RESULT_DIR = ROOT / "results" / EXPERIMENT_ID
DATA_DIR = ROOT / "data" / EXPERIMENT_ID
SYMBOL = "SOLUSDT"

TIMEFRAMES = [1, 3, 5]
AVERAGE_DAYS = [7, 15, 30]
ZONES = [0.25, 0.5, 0.75, 1.0]
APPROACHES = ["from_below", "any"]
FILTERS = ["avoid_strong_bearish", "bullish_only"]
STOPS = np.array([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
ACTIVATIONS = np.array([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
GIVEBACKS = np.array([10.0, 15.0, 20.0])
HOLDS_HOURS = [12, 24, 48, 72, None]
SIZINGS = [(1, 1.0), (1, 0.5), (2, 0.25), (2, 0.5), (3, 0.2), (3, 1 / 3), (4, 0.25), (5, 0.2)]
WAIT_MINUTES = 30
FEE = 10 / 10_000
SLIP = 2 / 10_000
INITIAL = 100.0
MAX_LOTS = max(lots for lots, _ in SIZINGS)
NEVER = np.iinfo(np.int64).max
CHUNK = 4_096
EDGE = 1e-12

UTC = "UTC"
PERIODS = {
    "earlier": (pd.Timestamp("2024-10-01", tz=UTC), pd.Timestamp("2025-09-01", tz=UTC)),
    "later": (pd.Timestamp("2025-09-01", tz=UTC), pd.Timestamp("2026-08-01", tz=UTC)),
    "holdout": (pd.Timestamp("2026-08-01", tz=UTC), pd.Timestamp("2026-09-10", tz=UTC)),
}
BASELINE = {"signal_minutes": 3, "average_days": 15, "zone_pct": 0.5, "approach": "from_below",
            "market_filter": "avoid_strong_bearish", "stop_pct": 4.0, "activation_pct": 4.0,
            "giveback_pct": 10.0, "hold_hours": 24, "lots": 2, "fraction": 0.25}

# Base exit paths without a hold limit: index = (stop * 7 + activation) * 3 + giveback.
BASE_PARAMS = [(s, a, g) for s in STOPS for a in ACTIVATIONS for g in GIVEBACKS]
EXIT_COMBOS = [(h, s, a, g) for h in HOLDS_HOURS for (s, a, g) in BASE_PARAMS]
EXIT_BASE_INDEX = np.tile(np.arange(len(BASE_PARAMS)), len(HOLDS_HOURS))
EXIT_HOLD_MINUTES = np.repeat(
    [h * 60 if h else NEVER for h in HOLDS_HOURS], len(BASE_PARAMS)
).astype(np.int64)
COMBO_LOTS = np.repeat([lots for lots, _ in SIZINGS], len(EXIT_COMBOS))
COMBO_FRACTION = np.repeat([fraction for _, fraction in SIZINGS], len(EXIT_COMBOS))
COMBOS = len(COMBO_LOTS)

# Worker globals (inherited through fork).
OPEN = HIGH = LOW = CLOSE = None
TABLE_IDX = TABLE_RAW = TABLE_CODE = None


def entry_configs() -> list[dict]:
    return [
        {"signal_minutes": tf, "average_days": days, "zone_pct": zone,
         "approach": approach, "market_filter": market_filter}
        for tf in TIMEFRAMES for days in AVERAGE_DAYS for zone in ZONES
        for approach in APPROACHES for market_filter in FILTERS
    ]


def load_market() -> tuple[pd.DataFrame, dict]:
    raw = replay.load_raw(SYMBOL, include_holdout=True)
    steps = pd.DatetimeIndex(raw.open_time).to_series().diff().iloc[1:]
    if not (steps == pd.Timedelta(minutes=1)).all():
        raise ValueError("SOL 1m history plus holdout is not continuous")
    daily = {
        day: tuple(float(v) if v is not None else np.nan for v in values)
        for day, values in replay.daily_averages(raw).items()
    }
    return raw, daily


def signal_frame(raw: pd.DataFrame, daily: dict, minutes: int) -> dict:
    indexed = raw.set_index("open_time")
    frame = indexed.resample(f"{minutes}min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )
    counts = indexed.close.resample(f"{minutes}min", label="left", closed="left").count()
    frame = frame[counts == minutes]
    if not (frame.index.to_series().diff().iloc[1:] == pd.Timedelta(minutes=minutes)).all():
        raise ValueError("Signal grid contains a gap")
    days = frame.index.floor("D")
    lookup = {day: daily.get(day, (np.nan,) * 3) for day in days.unique()}
    averages = np.array([lookup[day] for day in days])
    first_raw = int(pd.DatetimeIndex(raw.open_time).searchsorted(frame.index[0]))
    return {
        "open_time": frame.index,
        "open": frame.open.to_numpy(float), "high": frame.high.to_numpy(float),
        "low": frame.low.to_numpy(float), "close": frame.close.to_numpy(float),
        7: averages[:, 0], 15: averages[:, 1], 30: averages[:, 2],
        # Contiguous data: candle i starts at raw minute first_raw + i * minutes.
        "first_raw": first_raw,
    }


def fast_signals(frame: dict, config: dict) -> pd.DataFrame:
    """Vectorised FrozenSignalEngine: returns touch time and raw entry index."""
    minutes = config["signal_minutes"]
    zone = config["zone_pct"] / 100
    average = frame[config["average_days"]]
    high, low = frame["high"], frame["low"]
    # Stage 3 compares in exact Decimal; prices can land exactly on a band edge,
    # so floats get a relative tolerance that preserves the Decimal outcome.
    lower = average * (1 - zone)
    upper = average * (1 + zone)
    with np.errstate(invalid="ignore"):
        touched = np.isfinite(average) & (high >= lower * (1 - EDGE)) & (low <= upper * (1 + EDGE))
        prior_below = np.zeros(len(high), dtype=bool)
        prior_below[1:] = np.isfinite(average[:-1]) & (high[:-1] < lower[:-1] * (1 - EDGE))
        a7, a15, a30 = frame[7], frame[15], frame[30]
        missing = ~(np.isfinite(a7) & np.isfinite(a15) & np.isfinite(a30))
        bullish = ~missing & (a7 > a15) & (a15 > a30)
        bearish = ~missing & (a7 < a15) & (a15 < a30)
    new_episode = touched & ~np.r_[False, touched[:-1]]
    regime_ok = ~(bearish | missing) if config["market_filter"] == "avoid_strong_bearish" else bullish
    approach_ok = prior_below if config["approach"] == "from_below" else True
    eligible = new_episode & approach_ok & regime_ok
    bullish_candle = frame["close"] > frame["open"]
    max_steps = WAIT_MINUTES // minutes
    count = len(high)
    touches, confirmations = [], []
    for origin in np.flatnonzero(eligible):
        for offset in range(max_steps + 1):
            index = origin + offset
            if index >= count:
                break
            if bullish_candle[index]:
                touches.append(origin)
                confirmations.append(index)
                break
            if not touched[index]:
                break
    touches = np.asarray(touches, dtype=np.int64)
    confirmations = np.asarray(confirmations, dtype=np.int64)
    return pd.DataFrame({
        "touch_time": frame["open_time"][touches] if len(touches) else pd.DatetimeIndex([], tz=UTC),
        "entry_index": frame["first_raw"] + (confirmations + 1) * minutes,
    })


def _first_hits(entry: int, fill: float) -> tuple[np.ndarray, np.ndarray]:
    stops = fill * (1 - STOPS / 100)
    acts = fill * (1 + ACTIVATIONS / 100)
    stop_idx = np.full(len(STOPS), -1, dtype=np.int64)
    act_idx = np.full(len(ACTIVATIONS), -1, dtype=np.int64)
    run_min, run_max = np.inf, -np.inf
    position, count = entry, len(LOW)
    # The widest stop or the highest activation decides every stop/activation race.
    while position < count and stop_idx[-1] < 0 and act_idx[-1] < 0:
        end = min(position + CHUNK, count)
        cmin = np.minimum(np.minimum.accumulate(LOW[position:end]), run_min)
        cmax = np.maximum(np.maximum.accumulate(HIGH[position:end]), run_max)
        found = np.searchsorted(-cmin, -stops, side="left")
        update = (stop_idx < 0) & (found < len(cmin))
        stop_idx[update] = position + found[update]
        found = np.searchsorted(cmax, acts, side="left")
        update = (act_idx < 0) & (found < len(cmax))
        act_idx[update] = position + found[update]
        run_min, run_max, position = cmin[-1], cmax[-1], end
    return stop_idx, act_idx


def _trail_hits(activation: int, fill: float) -> list[tuple[int, float]]:
    results = [(-1, np.nan)] * len(GIVEBACKS)
    unresolved = set(range(len(GIVEBACKS)))
    peak = HIGH[activation]
    position, count = activation + 1, len(LOW)
    keep = (1 - GIVEBACKS / 100)[:, None]
    while position < count and unresolved:
        end = min(position + CHUNK, count)
        chunk_high = HIGH[position:end]
        prior = np.maximum.accumulate(np.r_[peak, chunk_high[:-1]])
        trails = fill + (prior - fill)[None, :] * keep
        hits = LOW[position:end][None, :] <= trails
        for g in tuple(unresolved):
            offset = np.flatnonzero(hits[g])
            if len(offset):
                results[g] = (position + int(offset[0]), float(trails[g, offset[0]]))
                unresolved.discard(g)
        peak = max(peak, float(chunk_high.max()))
        position = end
    return results


def exit_outcomes(entries: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """No-hold-limit exit for every stop/activation/giveback. Codes: 0 open,
    1 trailing, 2 protective stop, 3 ambiguous stop (stop wins)."""
    size = len(BASE_PARAMS)
    idx = np.full((len(entries), size), -1, dtype=np.int64)
    raw = np.full((len(entries), size), np.nan)
    code = np.zeros((len(entries), size), dtype=np.int8)
    for row, entry in enumerate(entries):
        fill = OPEN[entry] * (1 + SLIP)
        stop_idx, act_idx = _first_hits(int(entry), fill)
        stop_prices = fill * (1 - STOPS / 100)
        for j, activation in enumerate(act_idx):
            trails = None
            for k, stop in enumerate(stop_idx):
                base = (k * len(ACTIVATIONS) + j) * len(GIVEBACKS)
                if stop >= 0 and (activation < 0 or stop <= activation):
                    idx[row, base:base + len(GIVEBACKS)] = stop
                    raw[row, base:base + len(GIVEBACKS)] = min(stop_prices[k], OPEN[stop])
                    code[row, base:base + len(GIVEBACKS)] = 3 if stop == activation else 2
                elif activation >= 0:
                    if trails is None:
                        trails = _trail_hits(int(activation), fill)
                    for g, (hit, price) in enumerate(trails):
                        if hit >= 0:
                            idx[row, base + g] = hit
                            raw[row, base + g] = min(price, OPEN[hit])
                            code[row, base + g] = 1
    return idx, raw, code


def simulate(task: tuple[int, np.ndarray, np.ndarray]) -> dict[str, np.ndarray]:
    """Replay one entry config's signals for all 5,880 exit/hold/sizing combos."""
    _, entries, table_rows = task
    count = len(CLOSE)
    cash = np.full(COMBOS, INITIAL)
    active = np.zeros((COMBOS, MAX_LOTS), dtype=bool)
    exits = np.full((COMBOS, MAX_LOTS), NEVER, dtype=np.int64)
    qty = np.zeros((COMBOS, MAX_LOTS))
    cost = np.zeros((COMBOS, MAX_LOTS))
    unit = np.zeros((COMBOS, MAX_LOTS))
    kind = np.zeros((COMBOS, MAX_LOTS), dtype=np.int8)
    stats = {name: np.zeros(COMBOS) for name in [
        "trades", "wins", "losses", "gross_win", "gross_loss", "trailing_exits",
        "stop_exits", "time_exits", "ignored"]}
    peak = np.full(COMBOS, INITIAL)
    drawdown = np.zeros(COMBOS)
    rows = np.arange(COMBOS)

    def close_lots(mask: np.ndarray) -> None:
        nonlocal cash
        proceeds = np.where(mask, qty * unit, 0.0)
        pnl = np.where(mask, proceeds - cost, 0.0)
        cash = cash + proceeds.sum(1)
        stats["trades"] += mask.sum(1)
        stats["wins"] += (mask & (pnl > 0)).sum(1)
        stats["losses"] += (mask & (pnl < 0)).sum(1)
        stats["gross_win"] += np.where(pnl > 0, pnl, 0).sum(1)
        stats["gross_loss"] -= np.where(pnl < 0, pnl, 0).sum(1)
        stats["trailing_exits"] += (mask & (kind == 1)).sum(1)
        stats["stop_exits"] += (mask & ((kind == 2) | (kind == 3))).sum(1)
        stats["time_exits"] += (mask & (kind == 4)).sum(1)
        active[mask] = False

    for entry, table_row in zip(entries, table_rows):
        close_lots(active & (exits < entry))
        marked = cash + (qty * active).sum(1) * OPEN[entry]
        peak = np.maximum(peak, marked)
        drawdown = np.minimum(drawdown, marked / peak - 1)
        allocation = np.minimum(marked * COMBO_FRACTION, cash)
        can = (active.sum(1) < COMBO_LOTS) & (allocation > 1e-8)
        stats["ignored"] += ~can

        base_idx = TABLE_IDX[table_row][EXIT_BASE_INDEX]
        base_exit = np.where(base_idx < 0, NEVER, base_idx)
        hold_end = np.where(EXIT_HOLD_MINUTES == NEVER, NEVER, entry + EXIT_HOLD_MINUTES - 1)
        use_base = base_exit <= hold_end
        exit_idx = np.where(use_base, base_exit, np.where(hold_end < count, hold_end, NEVER))
        raw_exit = np.where(use_base, TABLE_RAW[table_row][EXIT_BASE_INDEX],
                            CLOSE[np.minimum(hold_end, count - 1)])
        exit_kind = np.where(use_base, TABLE_CODE[table_row][EXIT_BASE_INDEX], 4)
        exit_kind = np.where(exit_idx == NEVER, 0, exit_kind)
        fill = OPEN[entry] * (1 + SLIP)

        slot = np.argmin(active, axis=1)
        target = rows[can], slot[can]
        lot_qty = allocation / (fill * (1 + FEE))
        tiled = lambda values: np.tile(values, len(SIZINGS))  # noqa: E731
        qty[target] = lot_qty[can]
        cost[target] = allocation[can]
        exits[target] = tiled(exit_idx)[can]
        unit[target] = tiled(raw_exit * (1 - SLIP) * (1 - FEE))[can]
        kind[target] = tiled(exit_kind)[can]
        active[target] = True
        cash = cash - np.where(can, allocation, 0.0)

    close_lots(active & (exits < NEVER))
    open_value = (qty * active).sum(1) * CLOSE[-1]
    final = cash + open_value
    peak = np.maximum(peak, final)
    drawdown = np.minimum(drawdown, final / peak - 1)
    stats.update({
        "final_equity_usd": final,
        "approx_max_drawdown_pct": drawdown * 100,
        "open_at_end": active.sum(1).astype(float),
    })
    return stats


def main() -> None:
    global OPEN, HIGH, LOW, CLOSE, TABLE_IDX, TABLE_RAW, TABLE_CODE
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw, daily = load_market()
    OPEN, HIGH, LOW, CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    configs = entry_configs()

    frames = {tf: signal_frame(raw, daily, tf) for tf in TIMEFRAMES}
    signal_sets = []
    for config in configs:
        signals = fast_signals(frames[config["signal_minutes"]], config)
        signals = signals[signals.entry_index < len(OPEN)].reset_index(drop=True)
        signal_sets.append(signals)
    unique_entries = np.unique(np.concatenate([s.entry_index.to_numpy() for s in signal_sets]))
    print(f"signals ready: {sum(map(len, signal_sets)):,} across {len(configs)} configs, "
          f"{len(unique_entries):,} unique entries ({time.time() - started:.0f}s)", flush=True)

    context = mp.get_context("fork")
    with context.Pool(8) as pool:
        parts = pool.map(exit_outcomes, np.array_split(unique_entries, 64))
    TABLE_IDX = np.concatenate([p[0] for p in parts])
    TABLE_RAW = np.concatenate([p[1] for p in parts])
    TABLE_CODE = np.concatenate([p[2] for p in parts])
    print(f"exit paths ready ({time.time() - started:.0f}s)", flush=True)

    times = pd.DatetimeIndex(raw.open_time)
    tasks, keys = [], []
    for config_id, signals in enumerate(signal_sets):
        entry_times = times[signals.entry_index.to_numpy()]
        for period, (start, end) in PERIODS.items():
            mask = (signals.touch_time >= start).to_numpy() & (entry_times < end)
            entries = signals.entry_index.to_numpy()[mask]
            tasks.append((config_id, entries, np.searchsorted(unique_entries, entries)))
            keys.append((config_id, period))
    with context.Pool(8) as pool:
        results = pool.map(simulate, tasks, chunksize=4)
    print(f"portfolios ready ({time.time() - started:.0f}s)", flush=True)

    base = pd.DataFrame({
        "hold_hours": [h if h else 0 for h, *_ in EXIT_COMBOS] * len(SIZINGS),
        "stop_pct": [s for _, s, _, _ in EXIT_COMBOS] * len(SIZINGS),
        "activation_pct": [a for _, _, a, _ in EXIT_COMBOS] * len(SIZINGS),
        "giveback_pct": [g for *_, g in EXIT_COMBOS] * len(SIZINGS),
        "lots": COMBO_LOTS, "fraction": COMBO_FRACTION,
    })
    blocks = {}
    for (config_id, period), stats in zip(keys, results):
        block = blocks.setdefault(config_id, base.assign(**configs[config_id]))
        trades = stats["trades"]
        block[f"{period}_trades"] = trades.astype(int)
        block[f"{period}_wins"] = stats["wins"].astype(int)
        block[f"{period}_win_rate_pct"] = np.where(trades > 0, stats["wins"] / np.maximum(trades, 1) * 100, np.nan)
        block[f"{period}_final_usd"] = stats["final_equity_usd"]
        block[f"{period}_return_pct"] = stats["final_equity_usd"] - INITIAL
        block[f"{period}_profit_factor"] = np.where(
            stats["gross_loss"] > 0, stats["gross_win"] / np.maximum(stats["gross_loss"], 1e-12), np.nan)
        block[f"{period}_approx_dd_pct"] = stats["approx_max_drawdown_pct"]
        block[f"{period}_trail_stop_time"] = [
            f"{int(a)}/{int(b)}/{int(c)}" for a, b, c in
            zip(stats["trailing_exits"], stats["stop_exits"], stats["time_exits"])]
        block[f"{period}_ignored"] = stats["ignored"].astype(int)
    board = pd.concat(blocks.values(), ignore_index=True)
    board.to_parquet(RESULT_DIR / "all_combinations.parquet", index=False)
    print(f"saved {len(board):,} combinations ({time.time() - started:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
