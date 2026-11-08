"""Fixed-$100 micro-trail SOL strategy with giveback 12…30% (step 2).

Same rules as run_sol_fixed100_micro_trail_grid (the $300 / 3-lot / min($100,
cash) sizing, 7–15 day average, ±0.1…0.5% zone, stops −0.5…−2%, no time exit).
Each giveback is tested with the trail starting at +0.245% and at that
giveback's own break-even start (worst-case trail exit returns the stake).
"""

from __future__ import annotations

import json
import math
import time

import numpy as np
import pandas as pd

import run_sol_02_trail_stop_grid as g02
import run_sol_fixed100_micro_trail_grid as micro
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

EXPERIMENT_ID = "sol_fixed100_giveback_grid_v1"
RESULT_DIR = grid.ROOT / "results" / EXPERIMENT_ID
DATA_DIR = grid.ROOT / "data" / EXPERIMENT_ID

GIVEBACKS = [float(g) for g in range(12, 31, 2)]
FIXED_ACTIVATION = 0.245
# Worst case after activation: exit at fill × (1 + a × (1 − g)); costs need
# fill × 1.001 / (0.9998 × 0.999) to return the stake.
BREAK_EVEN = 1.001 / ((1 - grid.SLIP) * (1 - grid.FEE)) - 1


def break_even_activation(giveback: float) -> float:
    return math.ceil(BREAK_EVEN / (1 - giveback / 100) * 100 * 1000) / 1000


EXIT_SETS = [("fixed_0.245", FIXED_ACTIVATION, g) for g in GIVEBACKS] + [
    ("break_even", break_even_activation(g), g) for g in GIVEBACKS]
ACTIVATIONS = sorted({a for _, a, _ in EXIT_SETS})


def column_for(stop_index: int, activation: float, giveback: float) -> int:
    return ((stop_index * len(ACTIVATIONS) + ACTIVATIONS.index(activation))
            * len(GIVEBACKS) + GIVEBACKS.index(giveback))


def strategy_for(row: dict) -> dict:
    strategy = micro.strategy_for(row)
    strategy["strategy_id"] = "sol_fixed100_giveback"
    strategy["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] = float(row["activation_pct"])
    strategy["exit"]["trailing_stop"]["giveback_of_open_profit_pct"] = float(row["giveback_pct"])
    return strategy


def describe(row: dict) -> str:
    return (f"{micro.describe(row)}, trail from +{row['activation_pct']:g}% "
            f"with {row['giveback_pct']:g}% giveback")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = g02.load_all()
    windows = g02.periods(raw)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    grid.STOPS, grid.ACTIVATIONS, grid.GIVEBACKS = (np.array(micro.STOPS), np.array(ACTIVATIONS), np.array(GIVEBACKS))
    grid.BASE_PARAMS = [(s, a, g) for s in micro.STOPS for a in ACTIVATIONS for g in GIVEBACKS]
    times = pd.DatetimeIndex(raw.open_time)

    decimal_daily = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in decimal_daily.items()}
    extra = {n: {d: float(v) if v is not None else np.nan for d, v in replay.daily_average_n(raw, n).items()}
             for n in micro.AVERAGE_DAYS}
    signal_sets = {}
    for minutes in micro.TIMEFRAMES:
        frame = grid.signal_frame(raw, daily, minutes)
        days = frame["open_time"].floor("D")
        for n in micro.AVERAGE_DAYS:
            if n not in (7, 15):
                frame[n] = np.array([extra[n].get(d, np.nan) for d in days])
            for zone in micro.ZONES:
                config = {"signal_minutes": minutes, "average_days": n, "zone_pct": zone,
                          "approach": "from_below", "market_filter": "avoid_strong_bearish"}
                signals = grid.fast_signals(frame, config)
                signal_sets[(minutes, n, zone)] = signals[signals.entry_index < len(raw)].reset_index(drop=True)
    unique = np.unique(np.concatenate([s.entry_index.to_numpy() for s in signal_sets.values()]))
    grid.TABLE_IDX, grid.TABLE_RAW, grid.TABLE_CODE = grid.exit_outcomes(unique)
    print(f"{len(unique):,} entries, exits ready ({time.time() - started:.0f}s)", flush=True)

    rows = []
    for (minutes, n, zone), signals in signal_sets.items():
        entries = signals.entry_index.to_numpy()
        table_rows = np.searchsorted(unique, entries)
        masks = {period: (signals.touch_time >= start).to_numpy() & (times[entries] < end)
                 for period, (start, end) in windows.items()}
        for stop_index, stop in enumerate(micro.STOPS):
            for mode, activation, giveback in EXIT_SETS:
                column = column_for(stop_index, activation, giveback)
                row = {"signal_minutes": minutes, "average_days": n, "zone_pct": zone, "stop_pct": stop,
                       "trail_start_mode": mode, "activation_pct": activation, "giveback_pct": giveback}
                for period, mask in masks.items():
                    row.update({f"{period}_{k}": v for k, v in
                                micro.simulate(entries[mask], table_rows[mask], column).items()})
                rows.append(row)
    board = pd.DataFrame(rows).sort_values("full_profit_usd", ascending=False).reset_index(drop=True)
    board.insert(0, "rank", np.arange(1, len(board) + 1))
    board.to_csv(RESULT_DIR / f"all_{len(board)}_combinations.csv", index=False)
    print(f"grid done: {len(board):,} combinations ({time.time() - started:.0f}s)", flush=True)

    both = board[(board.earlier_profit_usd > 0) & (board.later_profit_usd > 0)]
    finalists = board.head(3).to_dict("records")
    if len(both) and int(both.iloc[0]["rank"]) > 3:
        finalists.append(both.iloc[0].to_dict())
    candle_cache: dict[tuple, list] = {}
    exact_rows = []
    for row in finalists:
        key = (int(row["signal_minutes"]), int(row["average_days"]))
        if key not in candle_cache:
            candle_cache[key] = replay.signal_candles(raw, key[0], decimal_daily, signal_days=key[1])
        strategy = strategy_for(row)
        signals, _ = replay.generate_signals(strategy, candle_cache[key])
        fast_count = len(signal_sets[(row["signal_minutes"], row["average_days"], row["zone_pct"])])
        for period, (start, end) in windows.items():
            result = replay.replay_execution(strategy, raw, signals, start, end, allocate=micro.lot_allocation)
            exact_rows.append({"rank": int(row["rank"]), "rules": describe(row), "period": period,
                               "exact_signals": len(signals), "fast_signals": fast_count,
                               **replay.summarize(result, initial=micro.INITIAL)})
            if period == "full":
                result.trades.to_csv(DATA_DIR / f"rank{int(row['rank'])}_full_trades.csv", index=False)
        print(f"exact: #{int(row['rank'])} {describe(row)} ({time.time() - started:.0f}s)", flush=True)
    exact = pd.DataFrame(exact_rows)
    exact.to_csv(RESULT_DIR / "exact_finalists.csv", index=False)
    (RESULT_DIR / "best_candidate_strategy.json").write_text(json.dumps(strategy_for(board.iloc[0]), indent=2) + "\n")

    pd.set_option("display.width", 250)
    cols = ["rank", "signal_minutes", "average_days", "zone_pct", "stop_pct", "activation_pct", "giveback_pct",
            "full_trades", "full_win_rate_pct", "full_profit_usd", "earlier_profit_usd", "later_profit_usd",
            "unseen_profit_usd", "full_approx_dd_pct", "full_fees_usd"]
    print(board[cols].head(15).round(2).to_string(index=False))
    board["gross"] = board.full_profit_usd + board.full_fees_usd + board.full_slippage_usd
    print(f"\nprofitable full: {(board.full_profit_usd > 0).sum()} / {len(board)} | positive earlier and later: "
          f"{len(both)} | positive before costs: {(board.gross > 0).sum()} | median full ${board.full_profit_usd.median():.2f}")
    for name in ["giveback_pct", "trail_start_mode", "stop_pct", "signal_minutes", "zone_pct", "average_days"]:
        print(name, board.groupby(name).full_profit_usd.median().round(1).to_dict())
    print(exact[["rank", "period", "exact_signals", "fast_signals", "trades", "win_rate_pct", "net_profit_usd",
                 "max_drawdown_pct", "average_winner_pct", "average_loser_pct", "fees_usd", "slippage_usd",
                 "trailing_exits", "stop_exits", "average_hold_hours"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
