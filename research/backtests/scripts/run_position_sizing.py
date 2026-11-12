"""Compare fixed, equity-percentage, and stop-risk sizing without leverage."""

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

from src.backtesting.position_sizing import (  # noqa: E402
    SizingSpec,
    planned_stop_loss_fraction,
    simulate_position_sizing,
    sizing_metrics,
)


RUN_ID = "step6_position_sizing_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
SOURCE = ROOT / "data/step5_realistic_costs_v1/costed_trades.parquet"
CONFIG = ROOT / "config/experiments/stage2_step6_position_sizing_v1.yaml"
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


def load_experiment() -> tuple[float, float, list[SizingSpec]]:
    config = yaml.safe_load(CONFIG.read_text())
    require(config["experiment"]["trading_mode"] == "long_only_spot", "Spot mode changed")
    require(not config["experiment"]["leverage_allowed"], "Leverage must remain disabled")
    initial = float(config["experiment"]["initial_equity_usd"])
    risk = config["risk_sizing"]
    stop_loss = planned_stop_loss_fraction(
        float(risk["protective_stop_pct_from_entry_fill"]),
        float(risk["fee_bps_per_side"]),
        float(risk["exit_slippage_bps"]),
    )
    variants = []
    for value in config["sizing_variants"]["fixed_capital_usd"]:
        variants.append(SizingSpec(f"fixed_${value:g}", "fixed_capital", float(value)))
    for value in config["sizing_variants"]["equity_fraction_pct"]:
        variants.append(SizingSpec(f"equity_{value:g}%", "equity_fraction", float(value) / 100))
    for value in config["sizing_variants"]["account_risk_pct"]:
        variants.append(SizingSpec(f"risk_{value:g}%", "risk_fraction", float(value) / 100))
    require(len(variants) == 9, "Unexpected sizing grid")
    return initial, stop_loss, variants


def run() -> None:
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    initial, stop_loss, variants = load_experiment()
    trades = pd.read_parquet(SOURCE).sort_values(["strategy", "entry_timestamp"])
    all_paths, rows = [], []
    scopes = {
        "full_history": pd.Series(True, index=trades.index),
        "earlier_reset": trades.entry_timestamp < SPLIT,
        "later_reset": trades.entry_timestamp >= SPLIT,
    }
    for strategy in ["primary", "control"]:
        strategy_trades = trades.loc[trades.strategy.eq(strategy)]
        for spec in variants:
            for scope, mask in scopes.items():
                current = strategy_trades.loc[mask.reindex(strategy_trades.index, fill_value=False)]
                path = simulate_position_sizing(current, spec, initial, stop_loss)
                path["scope"] = scope
                all_paths.append(path)
                rows.append({
                    "strategy": strategy,
                    "scope": scope,
                    "sizing_name": spec.name,
                    "sizing_method": spec.method,
                    "sizing_value": spec.value,
                    **sizing_metrics(path, initial),
                })

    paths = pd.concat(all_paths, ignore_index=True)
    summary = pd.DataFrame(rows)
    require(len(summary) == 2 * 3 * 9, "Unexpected summary size")
    require((paths.allocation_usd <= paths.equity_before_usd + 1e-12).all(),
            "Allocation exceeded available spot equity")
    require((paths.cash_reserve_usd >= -1e-12).all(), "Negative cash reserve")
    require(np.allclose(
        paths.equity_after_usd,
        paths.equity_before_usd + paths.net_pnl_usd,
        rtol=1e-12,
        atol=1e-12,
    ), "Equity reconciliation failed")

    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    paths.to_parquet(DATA / "sizing_paths.parquet", index=False)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    validation = {
        "step": "stage2_step6_position_sizing",
        "status": "PASS",
        "initial_equity_usd": initial,
        "sizing_variants": len(variants),
        "strategy_scope_comparisons": len(summary),
        "trade_path_rows_reconciled": len(paths),
        "planned_net_stop_loss_pct": stop_loss * 100,
        "leverage_used": False,
        "source_sha256": sha256(SOURCE),
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")

    primary = summary.loc[
        summary.strategy.eq("primary") & summary.scope.eq("full_history")
    ].sort_values("sizing_name")
    table_rows = []
    for row in primary.itertuples(index=False):
        table_rows.append(
            f"| {row.sizing_name} | ${row.final_equity_usd:.2f} | ${row.total_pnl_usd:+.2f} | "
            f"{row.total_return_pct:+.2f}% | {row.max_realized_drawdown_pct:.2f}% | "
            f"{row.mean_allocation_pct:.2f}% | ${row.total_fees_usd:.2f} |"
        )
    report = f"""# Stage 2 Step 6 — Position Sizing

## Method

All variants start with $100 and replay the same chronological, after-cost trades. Fixed sizing requests $25, $50, or $100 per trade and caps the request at current cash. Equity sizing invests 25%, 50%, or 100% of current equity. Risk sizing targets 0.5%, 1%, or 2% of equity at the planned stop.

The −4% stop becomes a **{stop_loss * 100:.4f}% planned cash loss** after exit slippage and both fees. Therefore the three risk settings allocate approximately {0.005 / stop_loss * 100:.2f}%, {0.01 / stop_loss * 100:.2f}%, and {0.02 / stop_loss * 100:.2f}% of equity. Gaps can still exceed the planned risk.

## Primary full-history results

| Sizing | Final equity | PnL | Return | Realized drawdown | Mean allocation | Fees paid |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(table_rows)}

## Interpretation

Higher allocation produced more profit and more drawdown because every variant used the same trades. The 100% equity variant is the most aggressive. Risk-based sizing ties exposure directly to the known stop: 1% account risk uses about {0.01 / stop_loss * 100:.2f}% of equity per trade, while keeping the rest in cash.

Drawdown here uses equity after each completed trade. Step 7 will add minute-by-minute mark-to-market equity, which can reveal deeper temporary drawdowns while positions are open.

Every allocation was capped at available cash. No leverage, borrowing, short selling, or simultaneous position was used.
"""
    (RESULTS / "REPORT.md").write_text(report)
    print(primary[[
        "sizing_name", "final_equity_usd", "total_pnl_usd", "total_return_pct",
        "max_realized_drawdown_pct", "mean_allocation_pct", "total_fees_usd",
    ]].to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()
