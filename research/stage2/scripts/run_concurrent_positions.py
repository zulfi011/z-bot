"""Jointly test concurrent-position limits and per-trade spot allocations."""

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

from src.backtesting.costs import apply_costs  # noqa: E402
from src.backtesting.multi_position import concurrent_metrics, simulate_concurrent_positions  # noqa: E402
from src.backtesting.position_sizing import SizingSpec  # noqa: E402
from src.backtesting.trailing import MAX_HOLD_MINUTES, simulate_fixed, simulate_trailing  # noqa: E402


STAGE1 = ROOT.parent / "stage1_research"
RUN_ID = "step6b_concurrent_positions_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
CONFIG = ROOT / "config/experiments/stage2_step6b_concurrent_positions_v1.yaml"
FROZEN = ROOT / "config/strategies/sol_15d_touch_v1.yaml"
FILLS = ROOT / "data/step3_entries_v1/entry_fills.parquet"
SPLIT = pd.Timestamp("2025-09-01", tz="UTC")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sizing_specs(config: dict) -> list[SizingSpec]:
    output = []
    variants = config["sizing_variants"]
    for value in variants["fixed_capital_usd"]:
        output.append(SizingSpec(f"fixed_${value:g}", "fixed_capital", float(value)))
    for value in variants["equity_fraction_pct"]:
        output.append(SizingSpec(f"equity_{value:g}%", "equity_fraction", float(value) / 100))
    for value in variants["account_risk_pct"]:
        output.append(SizingSpec(f"risk_{value:g}%", "risk_fraction", float(value) / 100))
    return output


def build_all_outcomes(fee_bps: float) -> tuple[pd.DataFrame, int]:
    fills = pd.read_parquet(FILLS).sort_values(["timestamp", "strategy", "signal_id"])
    raw_path = STAGE1 / "data/raw/SOLUSDT/SOLUSDT_1m.parquet"
    raw = pd.read_parquet(raw_path, columns=["open_time", "open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    rows = []
    incomplete = 0
    for fill in fills.itertuples(index=False):
        start = times.get_indexer([fill.timestamp])[0]
        require(start >= 0, "Entry is absent from raw candles")
        if start + MAX_HOLD_MINUTES > len(raw):
            incomplete += 1
            continue
        path = raw.iloc[start:start + MAX_HOLD_MINUTES]
        result = (simulate_trailing(path, 4.0, 10.0)
                  if fill.strategy == "primary" else simulate_fixed(path))
        require(np.isclose(result.entry_fill, fill.fill_price, rtol=0, atol=0),
                "Entry fill differs from Step 3")
        rows.append({
            "signal_id": fill.signal_id,
            "strategy": fill.strategy,
            "entry_timestamp": fill.timestamp,
            "exit_timestamp": fill.timestamp + pd.Timedelta(minutes=result.duration_minutes),
            "duration_minutes": result.duration_minutes,
            "exit_type": result.exit_type,
            "raw_entry_open": fill.raw_open,
            "entry_fill": result.entry_fill,
            "raw_exit_price": result.raw_exit,
            "exit_fill": result.exit_fill,
            "return_after_slippage_pct": (result.exit_fill / result.entry_fill - 1) * 100,
        })
    return apply_costs(pd.DataFrame(rows), fee_bps), incomplete


def run() -> None:
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    config = yaml.safe_load(CONFIG.read_text())
    frozen = yaml.safe_load(FROZEN.read_text())
    require(not config["experiment"]["leverage_allowed"], "Leverage must remain disabled")
    initial = float(config["experiment"]["initial_equity_usd"])
    limits = [int(value) for value in config["experiment"]["maximum_positions"]]
    variants = sizing_specs(config)
    stop_loss = float(config["risk_sizing"]["planned_net_stop_loss_pct"]) / 100
    fee_bps = float(frozen["execution"]["fee_bps_per_side"])
    outcomes, incomplete = build_all_outcomes(fee_bps)
    require(len(outcomes) == 909 and incomplete == 1, "Unexpected all-signal outcome count")

    scopes = {
        "full_history": pd.Series(True, index=outcomes.index),
        "earlier_reset": outcomes.entry_timestamp < SPLIT,
        "later_reset": outcomes.entry_timestamp >= SPLIT,
    }
    event_parts, rows = [], []
    for strategy in ["primary", "control"]:
        strategy_outcomes = outcomes.loc[outcomes.strategy.eq(strategy)]
        for scope, mask in scopes.items():
            current = strategy_outcomes.loc[mask.reindex(strategy_outcomes.index, fill_value=False)]
            for maximum in limits:
                for sizing in variants:
                    events = simulate_concurrent_positions(
                        current, sizing, initial, stop_loss, maximum
                    )
                    events["strategy"] = strategy
                    events["scope"] = scope
                    events["maximum_positions"] = maximum
                    events["sizing_name"] = sizing.name
                    events["sizing_method"] = sizing.method
                    events["sizing_value"] = sizing.value
                    event_parts.append(events)
                    rows.append({
                        "strategy": strategy,
                        "scope": scope,
                        "maximum_positions": maximum,
                        "sizing_name": sizing.name,
                        "sizing_method": sizing.method,
                        "sizing_value": sizing.value,
                        **concurrent_metrics(events, initial),
                    })

    events = pd.concat(event_parts, ignore_index=True)
    summary = pd.DataFrame(rows)
    require(len(summary) == 2 * 3 * len(limits) * len(variants), "Unexpected grid size")
    require((events.cash_usd >= -1e-10).all() and (events.deployment_pct <= 100 + 1e-10).all(),
            "Cash or leverage constraint failed")
    one_primary = summary.loc[
        summary.strategy.eq("primary") & summary.scope.eq("full_history")
        & summary.maximum_positions.eq(1) & summary.sizing_name.eq("equity_100%")
    ].iloc[0]
    one_control = summary.loc[
        summary.strategy.eq("control") & summary.scope.eq("full_history")
        & summary.maximum_positions.eq(1) & summary.sizing_name.eq("equity_100%")
    ].iloc[0]
    require(one_primary.opened_trades == 82 and np.isclose(one_primary.final_equity_usd, 130.844592),
            "One-position primary bridge failed")
    require(one_control.opened_trades == 117 and np.isclose(one_control.final_equity_usd, 118.438938),
            "One-position control bridge failed")

    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    outcomes.to_parquet(DATA / "all_signal_outcomes.parquet", index=False)
    events.to_parquet(DATA / "portfolio_events.parquet", index=False)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    validation = {
        "step": "stage2_step6b_concurrent_positions",
        "status": "PASS",
        "potential_complete_trade_outcomes": len(outcomes),
        "incomplete_signals_excluded": incomplete,
        "position_limits": limits,
        "sizing_variants": len(variants),
        "comparisons": len(summary),
        "portfolio_event_rows": len(events),
        "leverage_used": False,
        "one_position_primary_bridge_final_equity": one_primary.final_equity_usd,
        "one_position_control_bridge_final_equity": one_control.final_equity_usd,
        "source_sha256": sha256(FILLS),
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))
    primary = summary.loc[
        summary.strategy.eq("primary") & summary.scope.eq("full_history")
        & summary.sizing_name.isin(["risk_0.5%", "risk_1%", "risk_2%"])
    ]
    print(primary[["maximum_positions", "sizing_name", "opened_trades", "max_positions_observed",
                   "mean_allocation_usd", "final_equity_usd", "total_return_pct",
                   "max_book_drawdown_pct", "max_planned_open_risk_pct"]].to_string(index=False))


if __name__ == "__main__":
    run()

