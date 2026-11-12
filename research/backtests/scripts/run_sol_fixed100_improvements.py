"""Improvement tests for the fixed-$100 SOL candidate.

Base: 3m candles, 12-day average, ±0.5% zone, from below + confirmation, avoid
strong bearish, −2% stop, trail from +1.251% with 12% giveback, no time exit,
$300 account with up to 3 lots of min($100, free cash).

Ideas: trend filter, break-even stop, wider stops, skip 06–12 UTC entries,
neighbouring zones/averages. Tested one at a time, then all 1,440 combinations
with selection on the earlier period only; finalists re-run on the exact
Stage 3 replay at 10 bps, 7.5 bps (BNB) and 15/5 bps stress costs.
"""

from __future__ import annotations

import copy
import json
import time
from collections import Counter

import numpy as np
import pandas as pd

import run_sol_02_trail_stop_grid as g02
import run_sol_fixed100_giveback_grid as gb
import run_sol_fixed100_micro_trail_grid as micro
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

EXPERIMENT_ID = "sol_fixed100_improvements_v1"
RESULT_DIR = grid.ROOT / "results" / EXPERIMENT_ID

ACTIVATION = 1.251
GIVEBACK = 12.0
BE_LEVEL = round(gb.BREAK_EVEN * 100, 4)            # stop level that returns the stake
ZONES = [0.45, 0.5, 0.55]
AVERAGES = [11, 12, 13]
STOPS = [1.5, 2.0, 2.5, 3.0]
BE_TRIGGERS = [None, 0.5, 0.75, 1.0]
TRENDS = ["none", "bullish_regime", "above_30d", "above_30d_max10", "average_rising"]
MORNING = [False, True]
BASE = {"average_days": 12, "zone_pct": 0.5, "stop_pct": 2.0, "be_trigger": None,
        "trend": "none", "skip_06_12": False}
MIN_EARLIER_TRADES = 30
KIND = {1: "trailing", 2: "stop", 3: "stop", 5: "breakeven"}


def first_hit(start: int, level: float, above: bool, until: int | None = None) -> int:
    """First minute ≥ start whose high ≥ level (above) or low ≤ level; −1 if none by `until`."""
    series = grid.HIGH if above else grid.LOW
    end_all = len(series) if until is None else min(len(series), until + 1)
    position = start
    while position < end_all:
        end = min(position + grid.CHUNK, end_all)
        chunk = series[position:end]
        hits = np.flatnonzero(chunk >= level if above else chunk <= level)
        if len(hits):
            return position + int(hits[0])
        position = end
    return -1


def trail_exit(activation: int, fill: float) -> tuple[int, float]:
    peak, position, count = grid.HIGH[activation], activation + 1, len(grid.LOW)
    keep = 1 - GIVEBACK / 100
    while position < count:
        end = min(position + grid.CHUNK, count)
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


def exit_table(entries: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Exit index / raw price / kind for every stop × break-even trigger."""
    shape = (len(entries), len(STOPS) * len(BE_TRIGGERS))
    idx = np.full(shape, -1, dtype=np.int64)
    raw = np.full(shape, np.nan)
    code = np.zeros(shape, dtype=np.int8)
    for row, entry in enumerate(entries):
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        t_act = first_hit(entry, fill * (1 + ACTIVATION / 100), above=True)
        trail = trail_exit(t_act, fill) if t_act >= 0 else (-1, np.nan)
        horizon = t_act if t_act >= 0 else None
        stops = {s: first_hit(entry, fill * (1 - s / 100), above=False, until=horizon) for s in STOPS}
        be_price = fill * (1 + BE_LEVEL / 100)
        for b, trigger in enumerate(BE_TRIGGERS):
            t_trig = first_hit(entry, fill * (1 + trigger / 100), above=True, until=horizon) if trigger else -1
            t_be = (first_hit(t_trig + 1, be_price, above=False, until=horizon)
                    if trigger and t_trig >= 0 and t_trig != t_act else -1)
            for k, stop in enumerate(STOPS):
                column = k * len(BE_TRIGGERS) + b
                t_stop = stops[stop]
                first_guard = t_trig if (trigger and t_trig >= 0) else t_act
                if t_stop >= 0 and (first_guard < 0 or t_stop <= first_guard) and (t_act < 0 or t_stop <= t_act):
                    idx[row, column] = t_stop
                    raw[row, column] = min(fill * (1 - stop / 100), grid.OPEN[t_stop])
                    code[row, column] = 3 if t_stop == t_act else 2
                elif t_be >= 0 and (t_act < 0 or t_be <= t_act):
                    idx[row, column] = t_be
                    raw[row, column] = min(be_price, grid.OPEN[t_be])
                    code[row, column] = 5
                elif t_act >= 0 and trail[0] >= 0:
                    idx[row, column], raw[row, column], code[row, column] = trail[0], trail[1], 1
    return idx, raw, code


def simulate(entries: np.ndarray, rows: np.ndarray, column: int, tables) -> dict:
    idx_table, raw_table, code_table = tables
    cash, lots, pnl, kinds = micro.INITIAL, [], [], Counter()
    peak, drawdown = micro.INITIAL, 0.0
    for entry, row in zip(entries, rows):
        for lot in [lot for lot in lots if lot[0] < entry]:
            cash += lot[1] * lot[3]
            pnl.append(lot[1] * lot[3] - lot[2])
            kinds[KIND[lot[4]]] += 1
        lots = [lot for lot in lots if lot[0] >= entry]
        marked = cash + sum(lot[1] for lot in lots) * grid.OPEN[entry]
        peak = max(peak, marked)
        drawdown = min(drawdown, marked / peak - 1)
        allocation = min(micro.LOT_USD, cash)
        if len(lots) >= micro.MAX_LOTS or allocation <= 1e-8:
            continue
        fill = grid.OPEN[entry] * (1 + grid.SLIP)
        exit_index = idx_table[row, column]
        lots.append((micro.NEVER if exit_index < 0 else int(exit_index), allocation / (fill * (1 + grid.FEE)),
                     allocation, raw_table[row, column] * (1 - grid.SLIP) * (1 - grid.FEE),
                     int(code_table[row, column])))
        cash -= allocation
    for lot in lots:
        if lot[0] < micro.NEVER:
            cash += lot[1] * lot[3]
            pnl.append(lot[1] * lot[3] - lot[2])
            kinds[KIND[lot[4]]] += 1
    final = cash + sum(lot[1] for lot in lots if lot[0] == micro.NEVER) * grid.CLOSE[-1]
    drawdown = min(drawdown, final / max(peak, final) - 1)
    pnl = np.array(pnl)
    losses = -pnl[pnl < 0].sum()
    return {"trades": len(pnl), "win_rate_pct": (pnl > 0).mean() * 100 if len(pnl) else np.nan,
            "profit_usd": final - micro.INITIAL, "approx_dd_pct": drawdown * 100,
            "profit_factor": pnl[pnl > 0].sum() / losses if losses else np.nan,
            "trailing": kinds["trailing"], "stops": kinds["stop"], "breakeven": kinds["breakeven"]}


def features(signals: pd.DataFrame, daily: dict, extra: dict, times: pd.DatetimeIndex) -> pd.DataFrame:
    entry = signals.entry_index.to_numpy()
    confirm_day = times[entry - 3].floor("D")
    touch_day = pd.DatetimeIndex(signals.touch_time).floor("D")
    a7, a15, a30 = (np.array([daily.get(d, (np.nan,) * 3)[i] for d in touch_day]) for i in range(3))
    a30_confirm = np.array([daily.get(d, (np.nan,) * 3)[2] for d in confirm_day])
    stretch = grid.CLOSE[entry - 1] / a30_confirm - 1
    now = np.array([extra.get(d, np.nan) for d in confirm_day])
    before = np.array([extra.get(d - pd.Timedelta(days=3), np.nan) for d in confirm_day])
    hour = times[entry].hour
    return pd.DataFrame({
        "none": True,
        "bullish_regime": (a7 > a15) & (a15 > a30),
        "above_30d": stretch > 0,
        "above_30d_max10": (stretch > 0) & (stretch <= 0.10),
        "average_rising": now > before,
        "morning": (hour >= 6) & (hour < 12),
    })


def trigger_of(row: dict) -> float | None:
    value = row["be_trigger"]
    return None if value is None or pd.isna(value) else float(value)


def describe(row: dict) -> str:
    be = f"break-even stop after +{trigger_of(row):g}%" if trigger_of(row) else "no break-even stop"
    return (f"{int(row['average_days'])}-day avg, ±{row['zone_pct']:g}%, stop −{row['stop_pct']:g}%, {be}, "
            f"trend filter {row['trend']}, {'skip 06–12 UTC' if row['skip_06_12'] else 'all hours'}")


def strategy_for(row: dict, fee_bps: float = 10.0, slip_bps: float = 2.0) -> dict:
    strategy = micro.strategy_for({"signal_minutes": 3, "average_days": row["average_days"],
                                   "zone_pct": row["zone_pct"], "stop_pct": row["stop_pct"]})
    strategy["strategy_id"] = "sol_fixed100_improved"
    strategy["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] = ACTIVATION
    strategy["exit"]["trailing_stop"]["giveback_of_open_profit_pct"] = GIVEBACK
    strategy["execution_model"]["fee_bps_per_side"] = fee_bps
    strategy["execution_model"]["slippage_bps_per_side"] = slip_bps
    strategy["extensions"] = {"break_even_trigger_pct": trigger_of(row), "break_even_level_pct": BE_LEVEL,
                              "trend_filter": row["trend"], "skip_entries_06_12_utc": bool(row["skip_06_12"])}
    return strategy


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = g02.load_all()
    windows = g02.periods(raw)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    decimal_daily = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in decimal_daily.items()}
    extra = {n: {d: float(v) if v is not None else np.nan for d, v in replay.daily_average_n(raw, n).items()}
             for n in AVERAGES}
    frame = grid.signal_frame(raw, daily, 3)
    days = frame["open_time"].floor("D")
    sets = {}
    for n in AVERAGES:
        frame[n] = np.array([extra[n].get(d, np.nan) for d in days])
        for zone in ZONES:
            signals = grid.fast_signals(frame, {"signal_minutes": 3, "average_days": n, "zone_pct": zone,
                                                "approach": "from_below", "market_filter": "avoid_strong_bearish"})
            signals = signals[signals.entry_index < len(raw)].reset_index(drop=True)
            sets[(n, zone)] = (signals, features(signals, daily, extra[n], times))
    unique = np.unique(np.concatenate([s.entry_index.to_numpy() for s, _ in sets.values()]))
    tables = exit_table(unique)
    print(f"{len(unique):,} entries, exit paths ready ({time.time() - started:.0f}s)", flush=True)

    rows = []
    for (n, zone), (signals, feats) in sets.items():
        entries = signals.entry_index.to_numpy()
        table_rows = np.searchsorted(unique, entries)
        in_window = {p: (signals.touch_time >= s).to_numpy() & (times[entries] < e) for p, (s, e) in windows.items()}
        for trend in TRENDS:
            for skip in MORNING:
                keep = feats[trend].to_numpy() & ~(feats["morning"].to_numpy() & skip)
                for k, stop in enumerate(STOPS):
                    for b, trigger in enumerate(BE_TRIGGERS):
                        row = {"average_days": n, "zone_pct": zone, "stop_pct": stop, "be_trigger": trigger,
                               "trend": trend, "skip_06_12": skip}
                        for period, mask in in_window.items():
                            m = mask & keep
                            row.update({f"{period}_{key}": value for key, value in simulate(
                                entries[m], table_rows[m], k * len(BE_TRIGGERS) + b, tables).items()})
                        rows.append(row)
    board = pd.DataFrame(rows)
    board.to_csv(RESULT_DIR / "all_1440_combinations.csv", index=False)
    print(f"grid ready ({time.time() - started:.0f}s)", flush=True)

    def is_base(frame_: pd.DataFrame, **changes) -> pd.Series:
        target = {**BASE, **changes}
        mask = np.ones(len(frame_), dtype=bool)
        for key, value in target.items():
            mask &= frame_[key].isna().to_numpy() if value is None else (frame_[key] == value).to_numpy()
        return mask

    base_row = board[is_base(board)].iloc[0]
    single = []
    for name, values in [("trend", TRENDS), ("be_trigger", BE_TRIGGERS), ("stop_pct", STOPS),
                         ("skip_06_12", MORNING), ("zone_pct", ZONES), ("average_days", AVERAGES)]:
        for value in values:
            row = board[is_base(board, **{name: value})].iloc[0]
            single.append({"idea": name, "value": value,
                           **{f"{p}_{m}": row[f"{p}_{m}"] for p in windows for m in ["profit_usd", "trades"]},
                           "full_dd": row["full_approx_dd_pct"],
                           "helps_earlier": row["earlier_profit_usd"] > base_row["earlier_profit_usd"] + 0.005,
                           "helps_later": row["later_profit_usd"] > base_row["later_profit_usd"] + 0.005})
    single = pd.DataFrame(single)
    single.to_csv(RESULT_DIR / "one_at_a_time.csv", index=False)

    kept = {}
    for name in ["trend", "be_trigger", "stop_pct", "skip_06_12"]:
        helpful = single[(single.idea == name) & single.helps_earlier & single.helps_later]
        if len(helpful):
            best = helpful.sort_values("earlier_profit_usd", ascending=False).iloc[0]
            kept[name] = None if (name == "be_trigger" and pd.isna(best.value)) else best.value
    kept_row = board[is_base(board, **kept)].iloc[0]
    eligible = board[(board.earlier_trades >= MIN_EARLIER_TRADES) & (board.earlier_approx_dd_pct >= -15)]
    earlier_pick = eligible.sort_values("earlier_profit_usd", ascending=False).iloc[0]
    grid_view = board.copy()
    for key, value in {**BASE, **kept}.items():
        if key in ("zone_pct", "average_days"):
            continue
        grid_view = grid_view[grid_view[key].isna()] if value is None else grid_view[grid_view[key] == value]
    neighbourhood = grid_view.pivot_table(index="zone_pct", columns="average_days", values="full_profit_usd")

    finalists = {"BASE (candidate as-is)": base_row.to_dict(),
                 f"KEPT IDEAS COMBINED ({kept or 'none'})": kept_row.to_dict(),
                 "EARLIER-ONLY BEST of 1,440": earlier_pick.to_dict()}
    exact_rows = []
    candle_cache, signal_cache = {}, {}
    for label, row in finalists.items():
        n = int(row["average_days"])
        if n not in candle_cache:
            candle_cache[n] = replay.signal_candles(raw, 3, decimal_daily, signal_days=n)
        for costs, (fee, slip) in {"10/2 bps": (10.0, 2.0), "7.5/2 bps (BNB)": (7.5, 2.0),
                                   "15/5 bps stress": (15.0, 5.0)}.items():
            strategy = strategy_for(row, fee, slip)
            key = (n, row["zone_pct"])
            if key not in signal_cache:
                signal_cache[key], _ = replay.generate_signals(strategy, candle_cache[n])
            signals_, feats = sets[key]
            allowed = set(signals_.entry_index[feats[row["trend"]].to_numpy()
                                               & ~(feats["morning"].to_numpy() & bool(row["skip_06_12"]))])
            chosen = [s for s in signal_cache[key]
                      if times.searchsorted(pd.Timestamp(s["entry_time"])) in allowed]
            rule = replay.breakeven_exit(trigger_of(row), BE_LEVEL) if trigger_of(row) else None
            for period, (start, end) in windows.items():
                result = replay.replay_execution(strategy, raw, chosen, start, end,
                                                 allocate=micro.lot_allocation, exit_rule=rule)
                exact_rows.append({"finalist": label, "rules": describe(row), "costs": costs, "period": period,
                                   "exact_signals": len(signal_cache[key]), "fast_signals": len(signals_),
                                   **replay.summarize(result, initial=micro.INITIAL)})
        print(f"exact: {label} ({time.time() - started:.0f}s)", flush=True)
    exact = pd.DataFrame(exact_rows)
    exact.to_csv(RESULT_DIR / "exact_finalists.csv", index=False)
    (RESULT_DIR / "finalists.json").write_text(json.dumps(
        {k: {"rules": describe(v), "strategy": strategy_for(v)} for k, v in finalists.items()}, indent=2, default=str))

    pd.set_option("display.width", 250)
    print("\nBASE fast:", {k: round(base_row[k], 2) for k in ["full_profit_usd", "earlier_profit_usd",
                                                              "later_profit_usd", "unseen_profit_usd"]})
    print("\nONE AT A TIME\n" + single.round(2).to_string(index=False))
    print("\nKEPT:", kept)
    print("\nNEIGHBOURHOOD (full profit, other settings = base + kept)\n" + neighbourhood.round(2).to_string())
    top = eligible.sort_values("earlier_profit_usd", ascending=False).head(10)
    print("\nTOP 10 BY EARLIER\n" + top[["average_days", "zone_pct", "stop_pct", "be_trigger", "trend", "skip_06_12",
                                        "earlier_profit_usd", "later_profit_usd", "unseen_profit_usd",
                                        "full_profit_usd", "full_approx_dd_pct"]].round(2).to_string(index=False))
    print("\nEXACT\n" + exact[["finalist", "costs", "period", "exact_signals", "fast_signals", "trades",
                               "win_rate_pct", "net_profit_usd", "max_drawdown_pct", "profit_factor",
                               "trailing_exits", "stop_exits", "breakeven_exits"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
