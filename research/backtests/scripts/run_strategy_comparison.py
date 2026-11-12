"""Compare primary and control by period under conservative costs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.account import build_account_curve, select_spot_lots  # noqa: E402
from src.backtesting.performance import calculate_performance  # noqa: E402
from src.backtesting.scenarios import rebuild_cost_scenario_outcomes  # noqa: E402
from src.backtesting.trade_records import build_trade_records  # noqa: E402


RUN_ID = "step11_strategy_comparison_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
CONFIG = ROOT / "config/experiments/stage2_step11_comparison_v1.yaml"
RAW = ROOT.parent / "foundations/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
FILLS = ROOT / "data/step3_entries_v1/entry_fills.parquet"
STEP9 = ROOT / "results/step9_performance_v1/performance_metrics.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run() -> None:
    if DATA.exists() or RESULTS.exists():
        raise ValueError("Run already exists; refusing overwrite")
    config = yaml.safe_load(CONFIG.read_text())
    experiment = config["experiment"]
    split = pd.Timestamp(experiment["split_timestamp_utc"])
    initial = float(experiment["initial_equity_usd"])
    maximum = int(experiment["maximum_open_positions"])
    fraction = float(experiment["equity_fraction_per_entry"])
    require(experiment["trading_mode"] == "long_only_spot", "Spot mode changed")
    require(maximum == 2 and fraction == 0.25, "Frozen portfolio rule changed")

    raw = pd.read_parquet(RAW, columns=["open_time", "open", "high", "low", "close"])
    fills = pd.read_parquet(FILLS)
    rows = []
    record_parts = []
    incomplete_rows = []

    for cost in config["cost_scenarios"]:
        name = cost["name"]
        fee = float(cost["fee_bps_per_side"])
        slippage = float(cost["slippage_bps_per_side"])
        outcomes, incomplete = rebuild_cost_scenario_outcomes(
            fills, raw, fee, slippage
        )
        incomplete["cost_scenario"] = name
        incomplete_rows.append(incomplete)
        require(len(outcomes) == 909 and len(incomplete) == 1,
                f"Outcome count changed for {name}")

        for strategy in ["primary", "control"]:
            strategy_outcomes = outcomes.loc[outcomes.strategy.eq(strategy)]
            scope_masks = {
                "full_history": pd.Series(True, index=strategy_outcomes.index),
                "earlier_reset": strategy_outcomes.entry_timestamp < split,
                "later_reset": strategy_outcomes.entry_timestamp >= split,
            }
            for scope, mask in scope_masks.items():
                candidates = strategy_outcomes.loc[mask]
                selected = select_spot_lots(candidates, raw, initial, fraction, maximum)
                if scope == "later_reset":
                    curve_candles = raw.loc[raw.open_time >= split]
                elif scope == "earlier_reset":
                    final_open = selected.exit_timestamp.max() - pd.Timedelta(minutes=1)
                    curve_candles = raw.loc[raw.open_time <= final_open]
                else:
                    curve_candles = raw
                curve = build_account_curve(curve_candles, selected, initial)
                records = build_trade_records(selected)
                metrics = calculate_performance(records, curve, initial)
                require(curve.cash_usd.min() >= -1e-10, "Negative cash")
                require(curve.open_positions.max() <= maximum, "Position limit exceeded")
                require(curve.open_positions.iloc[-1] == 0, "Position left open")

                records.insert(0, "scope", scope)
                records.insert(0, "slippage_bps_per_side", slippage)
                records.insert(0, "fee_bps_per_side", fee)
                records.insert(0, "cost_scenario", name)
                record_parts.append(records)
                rows.append({
                    "cost_scenario": name,
                    "fee_bps_per_side": fee,
                    "slippage_bps_per_side": slippage,
                    "strategy": strategy,
                    "scope": scope,
                    "candidate_signals": len(candidates),
                    "opened_trades": metrics["trades"],
                    "wins": metrics["wins"],
                    "losses": metrics["losses"],
                    "win_rate_pct": metrics["win_rate_pct"],
                    "profit_factor": metrics["profit_factor"],
                    "average_trade_return_pct": metrics["average_trade_return_pct"],
                    "average_trade_pnl_usd": metrics["average_trade_pnl_usd"],
                    "worst_trade_return_pct": metrics["worst_trade_return_pct"],
                    "final_equity_usd": metrics["final_equity_usd"],
                    "total_pnl_usd": metrics["total_pnl_usd"],
                    "total_return_pct": metrics["total_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "lowest_equity_usd": metrics["lowest_equity_usd"],
                    "total_fees_usd": records.total_fees_usd.sum(),
                    "total_slippage_usd": records.total_slippage_usd.sum(),
                })

    summary = pd.DataFrame(rows)
    records = pd.concat(record_parts, ignore_index=True)
    incomplete = pd.concat(incomplete_rows, ignore_index=True)
    require(len(summary) == 30, "Comparison grid is incomplete")

    baseline_reference = json.loads(STEP9.read_text())
    for strategy in ["primary", "control"]:
        actual = summary.loc[
            summary.cost_scenario.eq("baseline")
            & summary.strategy.eq(strategy)
            & summary.scope.eq("full_history")
        ].iloc[0]
        reference = baseline_reference[strategy]
        require(np.isclose(actual.final_equity_usd, reference["final_equity_usd"],
                           rtol=1e-12, atol=1e-12),
                f"Baseline equity changed for {strategy}")
        require(np.isclose(actual.max_drawdown_pct, reference["max_drawdown_pct"],
                           rtol=1e-12, atol=1e-12),
                f"Baseline drawdown changed for {strategy}")

    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    records.to_parquet(DATA / "scenario_trade_records.parquet", index=False)
    incomplete.to_csv(DATA / "incomplete_signals.csv", index=False)
    summary.to_csv(RESULTS / "comparison.csv", index=False)
    validation = {
        "step": "stage2_step11_strategy_comparison",
        "status": "PASS",
        "cost_scenarios": len(config["cost_scenarios"]),
        "comparison_rows": len(summary),
        "strategies": ["primary", "control"],
        "scopes": config["scopes"],
        "outcomes_rebuilt_from_raw_per_scenario": 909,
        "baseline_matches_step9": True,
        "maximum_positions": maximum,
        "leverage_used": False,
        "raw_source_sha256": sha256(RAW),
        "entry_source_sha256": sha256(FILLS),
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    view = summary.loc[summary.scope.ne("full_history"), [
        "cost_scenario", "strategy", "scope", "opened_trades", "win_rate_pct",
        "profit_factor", "total_return_pct", "max_drawdown_pct",
    ]]
    print(view.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()

