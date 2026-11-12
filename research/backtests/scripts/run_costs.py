"""Apply frozen spot fees to every completed Stage 2 trade."""

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


RUN_ID = "step5_realistic_costs_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
SOURCE = ROOT / "data/step4_exits_v1/completed_trades.parquet"
REFERENCE = ROOT / "data/trailing_activation_grid_v1/trades.parquet"
CONFIG = ROOT / "config/strategies/sol_15d_touch_v1.yaml"
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


def metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    values = frame.net_return_pct
    positive = values[values > 0].sum()
    negative = abs(values[values < 0].sum())
    compounded = np.prod(1 + values.to_numpy() / 100)
    return {
        "trades": len(frame),
        "wins": int(values.gt(0).sum()),
        "losses_or_zero": int(values.le(0).sum()),
        "win_rate_pct": values.gt(0).mean() * 100,
        "mean_gross_raw_return_pct": frame.gross_raw_return_pct.mean(),
        "mean_after_slippage_pct": frame.return_after_slippage_pct.mean(),
        "mean_net_return_pct": values.mean(),
        "median_net_return_pct": values.median(),
        "profit_factor": positive / negative,
        "illustrative_full_reinvestment_return_pct": (compounded - 1) * 100,
        "mean_slippage_drag_pct_points": frame.slippage_drag_pct_points.mean(),
        "mean_fee_drag_pct_points": frame.fee_drag_pct_points.mean(),
        "mean_total_execution_drag_pct_points": frame.total_execution_drag_pct_points.mean(),
    }


def validate_reference(costed: pd.DataFrame) -> int:
    reference = pd.read_parquet(REFERENCE)
    parts = []
    for strategy, variant in [("primary", "trail_a4_g10"), ("control", "fixed_4")]:
        parts.append(reference.loc[
            reference.strategy.eq(strategy) & reference.variant.eq(variant)
        ])
    expected = pd.concat(parts).sort_values(["strategy", "entry_timestamp"]).reset_index(drop=True)
    actual = costed.sort_values(["strategy", "entry_timestamp"]).reset_index(drop=True)
    require(len(actual) == len(expected), "Cost reference count mismatch")
    pd.testing.assert_series_equal(actual.entry_timestamp, expected.entry_timestamp, check_names=False)
    require(np.allclose(actual.net_return_pct, expected.net_return_pct, rtol=1e-12, atol=1e-12),
            "Net cost return differs from independent reference")
    return len(actual)


def run() -> None:
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    config = yaml.safe_load(CONFIG.read_text())
    fee_bps = float(config["execution"]["fee_bps_per_side"])
    slippage_bps = float(config["execution"]["slippage_bps_per_side"])
    require(slippage_bps == 2.0, "Frozen slippage assumption changed")
    source = pd.read_parquet(SOURCE)
    costed = apply_costs(source, fee_bps)
    reference_checks = validate_reference(costed)

    costed["period"] = np.where(costed.entry_timestamp < SPLIT, "earlier", "later")
    rows = []
    for strategy, group in costed.groupby("strategy", sort=True):
        for period in ["earlier", "later", "combined"]:
            current = group if period == "combined" else group.loc[group.period.eq(period)]
            rows.append({"strategy": strategy, "period": period, **metrics(current)})
    summary = pd.DataFrame(rows)

    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    costed.to_parquet(DATA / "costed_trades.parquet", index=False)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    validation = {
        "step": "stage2_step5_realistic_costs",
        "status": "PASS",
        "completed_trades_costed": len(costed),
        "trades_matched_to_independent_reference": reference_checks,
        "fee_bps_per_side": fee_bps,
        "slippage_bps_per_side": slippage_bps,
        "source_sha256": sha256(SOURCE),
        "reference_sha256": sha256(REFERENCE),
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")

    primary = summary.loc[
        summary.strategy.eq("primary") & summary.period.eq("combined")
    ].iloc[0]
    control = summary.loc[
        summary.strategy.eq("control") & summary.period.eq("combined")
    ].iloc[0]
    report = f"""# Stage 2 Step 5 — Realistic Trading Costs

## Cost model

Each trade uses the already recorded 2 bps adverse buy fill and 2 bps adverse sell fill. A 10 bps spot fee is then charged on the slipped entry value and another 10 bps on the slipped exit value. There is no leverage, funding, borrowing, or liquidation cost.

## Results after all costs

| Strategy | Trades | Wins | Win rate | Mean raw | After slippage | After fees | Profit factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| Primary | {primary.trades:.0f} | {primary.wins:.0f} | {primary.win_rate_pct:.2f}% | {primary.mean_gross_raw_return_pct:+.3f}% | {primary.mean_after_slippage_pct:+.3f}% | {primary.mean_net_return_pct:+.3f}% | {primary.profit_factor:.3f} |
| Control | {control.trades:.0f} | {control.wins:.0f} | {control.win_rate_pct:.2f}% | {control.mean_gross_raw_return_pct:+.3f}% | {control.mean_after_slippage_pct:+.3f}% | {control.mean_net_return_pct:+.3f}% | {control.profit_factor:.3f} |

The primary's average execution drag was {abs(primary.mean_total_execution_drag_pct_points):.3f} percentage points per trade: approximately {abs(primary.mean_slippage_drag_pct_points):.3f} from slippage and {abs(primary.mean_fee_drag_pct_points):.3f} from fees.

## Accounting

The output retains per-unit entry fee, exit fee, entry slippage, exit slippage, cash paid, cash received, and net PnL for every trade. Dollar PnL is deferred until Step 6 defines position size. The illustrative compounded return assumes the full account is reinvested each time and is not yet the final account simulation.

All {reference_checks} final net returns matched the independent realistic-cost analysis exactly.
"""
    (RESULTS / "REPORT.md").write_text(report)
    print(summary.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()
