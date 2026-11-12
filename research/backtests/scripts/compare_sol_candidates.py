"""Exact Stage 3 replay of SOL strategies on a common $300 account and windows."""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd

import run_sol_02_trail_stop_grid as g02
import run_sol_fixed100_micro_trail_grid as micro
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

RESULT_DIR = grid.ROOT / "results" / "sol_comparison_v1"
INITIAL = 300.0


def with_equity(strategy: dict) -> dict:
    strategy = copy.deepcopy(strategy)
    strategy["portfolio"]["initial_paper_equity_usd"] = INITIAL
    return strategy


def fixed100_candidate() -> dict:
    return micro.strategy_for({"signal_minutes": 3, "average_days": 12, "zone_pct": 0.5, "stop_pct": 2.0}) | {}


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = g02.load_all()
    windows = g02.periods(raw)
    averages = replay.daily_averages(raw)

    current = with_equity(json.loads(replay.STRATEGY_FILES[grid.SYMBOL].read_text()))
    single_lot = with_equity(json.loads(g02.PROPOSED.read_text()))
    fixed = fixed100_candidate()
    fixed["exit"]["trailing_stop"]["activation_pct_from_entry_fill"] = 1.251
    fixed["exit"]["trailing_stop"]["giveback_of_open_profit_pct"] = 12.0
    strategies = {
        "Current live (±0.5%, 15d, 2×25%, −4%/+4%/10%, 24h)": (current, None, None),
        "New fixed-$100 (±0.5%, 12d, 3×$100, −2%/+1.251%/12%, no time)": (fixed, micro.lot_allocation, 12),
        "Reference 1×50% candidate": (single_lot, None, None),
    }

    rows = []
    for name, (strategy, allocate, days) in strategies.items():
        candles = replay.signal_candles(raw, int(strategy["market"]["signal_timeframe"].removesuffix("m")),
                                        averages, signal_days=days)
        signals, _ = replay.generate_signals(strategy, candles)
        for period, (start, end) in windows.items():
            result = replay.replay_execution(strategy, raw, signals, start, end, allocate=allocate)
            summary = replay.summarize(result, initial=INITIAL)
            trades = result.trades
            minutes = (end - start) / pd.Timedelta(minutes=1)
            invested = float((trades.allocation_usd * trades.duration_minutes).sum()) if len(trades) else 0.0
            rows.append({"strategy": name, "period": period, **summary,
                         "average_invested_pct": invested / (INITIAL * minutes) * 100,
                         "return_per_drawdown": summary["return_pct"] / -summary["max_drawdown_pct"]
                         if summary["max_drawdown_pct"] < 0 else np.nan})
        print(f"done: {name}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(RESULT_DIR / "comparison.csv", index=False)
    pd.set_option("display.width", 250)
    for metric in ["trades", "win_rate_pct", "net_profit_usd", "return_pct", "max_drawdown_pct",
                   "profit_factor", "average_winner_pct", "average_loser_pct", "fees_usd", "slippage_usd",
                   "average_hold_hours", "average_invested_pct", "return_per_drawdown", "lowest_equity_usd",
                   "trailing_exits", "stop_exits", "time_exits"]:
        print(f"\n{metric}")
        print(frame.pivot(index="strategy", columns="period", values=metric)[list(windows)].round(2).to_string())


if __name__ == "__main__":
    main()
