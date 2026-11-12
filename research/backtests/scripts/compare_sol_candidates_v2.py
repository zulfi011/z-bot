"""Exact Stage 3 replay of the current SOL strategy vs the filtered fixed-$100
candidates (and the 1×50% reference) on a $300 account, at three cost levels."""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd

import run_sol_02_trail_stop_grid as g02
import run_sol_fixed100_filtered_grid as filtered
import run_sol_fixed100_improvements as imp
import run_sol_fixed100_micro_trail_grid as micro
import run_sol_stage3_space_grid as grid
import stage3_replay as replay

RESULT_DIR = grid.ROOT / "results" / "sol_comparison_v2"
INITIAL = 300.0
COSTS = {"10/2 bps": (10.0, 2.0), "7.5/2 bps (BNB)": (7.5, 2.0), "15/5 bps stress": (15.0, 5.0)}
CANDIDATE = {"average_days": 12, "zone_pct": 0.5, "stop_pct": 2.0, "be_trigger": None}


def with_costs(strategy: dict, fee: float, slip: float) -> dict:
    strategy = copy.deepcopy(strategy)
    strategy["portfolio"]["initial_paper_equity_usd"] = INITIAL
    strategy["execution_model"]["fee_bps_per_side"] = fee
    strategy["execution_model"]["slippage_bps_per_side"] = slip
    return strategy


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    raw = g02.load_all()
    windows = g02.periods(raw)
    times = pd.DatetimeIndex(raw.open_time)
    grid.OPEN, grid.HIGH, grid.LOW, grid.CLOSE = (raw[c].to_numpy(float) for c in ["open", "high", "low", "close"])
    decimal_daily = replay.daily_averages(raw)
    daily = {d: tuple(float(v) if v is not None else np.nan for v in vals) for d, vals in decimal_daily.items()}

    candles_3m = replay.signal_candles(raw, 3, decimal_daily)
    candles_12d = replay.signal_candles(raw, 3, decimal_daily, signal_days=12)
    new_base = imp.strategy_for({**CANDIDATE, "trend": "none", "skip_06_12": False})
    new_signals, _ = replay.generate_signals(new_base, candles_12d)
    entry_index = np.array([times.searchsorted(pd.Timestamp(s["entry_time"])) for s in new_signals])
    frame = pd.DataFrame({"entry_index": entry_index})
    above, morning = filtered.filter_masks(frame, 3, daily, times)
    live = json.loads(replay.STRATEGY_FILES[grid.SYMBOL].read_text())
    live_signals, _ = replay.generate_signals(live, candles_3m)

    strategies = {
        "Current live (2×25%, −4% / +4% / 10%, 24h)": (live, live_signals, None),
        "Reference 1×50% candidate": (json.loads(g02.PROPOSED.read_text()), live_signals, None),
        "New best: skip 06–12 UTC": (new_base, [s for s, m in zip(new_signals, morning) if not m], micro.lot_allocation),
        "New lower-risk: skip 06–12 + above 30d": (
            new_base, [s for s, a, m in zip(new_signals, above, morning) if a and not m], micro.lot_allocation),
    }
    rows = []
    for name, (strategy, signals, allocate) in strategies.items():
        for costs, (fee, slip) in COSTS.items():
            configured = with_costs(strategy, fee, slip)
            for period, (start, end) in windows.items():
                result = replay.replay_execution(configured, raw, signals, start, end, allocate=allocate)
                summary = replay.summarize(result, initial=INITIAL)
                rows.append({"strategy": name, "costs": costs, "period": period, **summary,
                             "return_per_drawdown": summary["return_pct"] / -summary["max_drawdown_pct"]
                             if summary["max_drawdown_pct"] < 0 else np.nan})
        print(f"done: {name}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(RESULT_DIR / "comparison.csv", index=False)
    pd.set_option("display.width", 250)
    base = frame[frame.costs == "10/2 bps"]
    for metric in ["trades", "win_rate_pct", "net_profit_usd", "max_drawdown_pct", "profit_factor",
                   "return_per_drawdown", "average_winner_pct", "average_loser_pct", "fees_usd", "slippage_usd",
                   "trades_per_month", "average_hold_hours", "lowest_equity_usd"]:
        print(f"\n{metric}\n" + base.pivot(index="strategy", columns="period", values=metric)[list(windows)]
              .round(2).to_string())
    print("\nprofit by costs (full / earlier / later / unseen)")
    print(frame.pivot_table(index=["strategy", "costs"], columns="period", values="net_profit_usd", sort=False)
          [list(windows)].round(2).to_string())


if __name__ == "__main__":
    main()
