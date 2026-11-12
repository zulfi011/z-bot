"""Assemble the validated Stage 2 evidence and paper-trading decision."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUTPUT = RESULTS / "stage2_final_report_v1"
PERFORMANCE = RESULTS / "step9_performance_v1/performance_metrics.json"
COMPARISON = RESULTS / "step11_strategy_comparison_v1/comparison.csv"
STRICT = RESULTS / "step10_strict_validation_v1/validation.json"
STRATEGY = ROOT / "config/strategies/sol_15d_touch_v1.yaml"
VALIDATIONS = [
    RESULTS / "step2_chronological_engine_v1/validation.json",
    RESULTS / "step3_entries_v1/validation.json",
    RESULTS / "step4_exits_v1/validation.json",
    RESULTS / "step5_realistic_costs_v1/validation.json",
    RESULTS / "step6_position_sizing_v1/validation.json",
    RESULTS / "step6b_concurrent_positions_v1/validation.json",
    RESULTS / "step7_account_tracking_v1/validation.json",
    RESULTS / "step8_trade_records_v1/validation.json",
    RESULTS / "step9_performance_v1/validation.json",
    RESULTS / "step10_strict_validation_v1/validation.json",
    RESULTS / "step11_strategy_comparison_v1/validation.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    if (OUTPUT / "validation.json").exists():
        raise ValueError("Final Stage 2 report already exists; refusing overwrite")
    statuses = {path.parent.name: json.loads(path.read_text())["status"] for path in VALIDATIONS}
    require(all(status == "PASS" for status in statuses.values()),
            "A Stage 2 validation did not pass")

    performance = json.loads(PERFORMANCE.read_text())
    strict = json.loads(STRICT.read_text())
    comparison = pd.read_csv(COMPARISON)
    primary = performance["primary"]
    control = performance["control"]
    conservative = comparison.loc[
        comparison.cost_scenario.eq("conservative")
    ].set_index(["strategy", "scope"])
    severe = comparison.loc[
        comparison.cost_scenario.eq("severe_stress")
    ].set_index(["strategy", "scope"])
    indexed = comparison.set_index(["cost_scenario", "scope", "strategy"])
    advantages = []
    for cost, scope in comparison[["cost_scenario", "scope"]].drop_duplicates().itertuples(index=False):
        advantages.append(
            indexed.loc[(cost, scope, "primary"), "total_return_pct"]
            > indexed.loc[(cost, scope, "control"), "total_return_pct"]
        )

    require(primary["total_pnl_usd"] > 0, "Primary baseline is not profitable")
    require(conservative.loc[("primary", "earlier_reset"), "total_return_pct"] > 0,
            "Primary failed conservative earlier period")
    require(conservative.loc[("primary", "later_reset"), "total_return_pct"] > 0,
            "Primary failed conservative later period")
    require(all(advantages), "Primary did not beat control in every comparison")
    require(strict["status"] == "PASS", "Strict validation failed")

    decision = {
        "stage": "V1 Stage 2",
        "status": "complete",
        "paper_trading_decision": "GO_WITH_GUARDRAILS",
        "real_money_decision": "NO_GO",
        "selected_strategy": "primary",
        "control_strategy": "control",
        "decision_date_utc": "2026-09-08",
        "reason": (
            "Primary is positive in both periods under conservative costs, beats the "
            "control in all matched comparisons, and passed strict mechanical validation. "
            "The small edge and material drawdown still require forward paper validation."
        ),
        "paper_starting_equity_usd": 100.0,
        "maximum_open_positions": 2,
        "equity_fraction_per_entry": 0.25,
        "review_thresholds": {
            "minimum_calendar_days": 180,
            "minimum_completed_trades": 50,
            "net_pnl_must_be_positive": True,
            "profit_factor_minimum": 1.0,
            "maximum_drawdown_review_pct": 15.0,
            "maximum_average_round_trip_cost_bps": 40.0,
            "strategy_rule_mismatches_allowed": 0,
        },
    }

    report = f"""# V1 Stage 2 Backtesting Report

## Decision

**GO WITH GUARDRAILS for simulated paper trading. NO-GO for real-money trading.**

The primary strategy is ready to be tested against live market data without capital. It is not yet proven strongly enough for real money. Its historical edge is positive but small, and prior statistical confidence intervals crossed zero.

## Frozen Paper Strategy

- Trade SOLUSDT spot, long only; no leverage or shorting.
- Use the 3-minute touch-from-below signal around the completed-close 15-day SMA with a ±0.5% zone.
- Require a bullish confirmation within 30 minutes and reject the strongly bearish 7D < 15D < 30D condition.
- Enter at the next signal boundary with adverse slippage.
- Use a -4% protective stop and a 24-hour maximum hold.
- At +4% open profit, activate a trail that gives back 10% of the peak open profit.
- Allow at most two positions; allocate 25% of current marked equity to each.
- Baseline execution assumes 10 bps fee and 2 bps slippage per side.

## Baseline Performance

| Metric | Primary | Control |
|---|---:|---:|
| Starting equity | $100.00 | $100.00 |
| Final equity | ${primary['final_equity_usd']:.2f} | ${control['final_equity_usd']:.2f} |
| Net PnL | +${primary['total_pnl_usd']:.2f} | +${control['total_pnl_usd']:.2f} |
| Trades | {primary['trades']} | {control['trades']} |
| Win rate | {primary['win_rate_pct']:.2f}% | {control['win_rate_pct']:.2f}% |
| Profit factor | {primary['profit_factor']:.2f} | {control['profit_factor']:.2f} |
| Average trade return | {primary['average_trade_return_pct']:+.3f}% | {control['average_trade_return_pct']:+.3f}% |
| Worst trade | {primary['worst_trade_return_pct']:.2f}% | {control['worst_trade_return_pct']:.2f}% |
| Maximum drawdown | {primary['max_drawdown_pct']:.2f}% | {control['max_drawdown_pct']:.2f}% |

The primary won {primary['wins']} of {primary['trades']} trades. Its lowest marked equity was ${primary['lowest_equity_usd']:.2f}. The largest drawdown took approximately nine months to recover, showing that profitable results may still include long weak periods.

## Period and Cost Robustness

At baseline costs, the primary returned +3.76% in the earlier period and +4.41% in the later period. Under conservative 15 bps fees and 5 bps slippage per side, it remained positive at **{conservative.loc[('primary', 'earlier_reset'), 'total_return_pct']:+.2f}% earlier** and **{conservative.loc[('primary', 'later_reset'), 'total_return_pct']:+.2f}% later**. The control lost money in both conservative periods.

The primary beat the control in all 15 matched strategy, period, and cost comparisons. Under severe 20/10 bps costs, the primary lost **{severe.loc[('primary', 'full_history'), 'total_return_pct']:.2f}%**, so its advantage is sensitive to poor execution.

## Validation Evidence

- 1,006,560 raw one-minute candles processed chronologically.
- 20 future-data access probes blocked.
- All 361 primary and control exits independently reconstructed from raw candles.
- Fees, slippage, and cash flows recalculated for all 361 trades.
- 2,013,120 account rows reconciled with an economically zero maximum error.
- Two-position, spot-cash, and conservative same-candle rules passed.
- Baseline cost comparison exactly reproduced the final performance result.

## Risks and Limits

The strategy was selected after substantial historical refinement, creating selection-bias risk. One-minute OHLC cannot reproduce order-book depth, latency, outages, or exact intraminute order. Modeled costs consumed much of the gross advantage. The 1.18 baseline profit factor and 8.33% return over roughly 23 months leave little room for worse live execution.

## Paper-Trading Gate

Run the frozen rules without changes for at least 180 calendar days and 50 completed trades. Before considering real capital, require positive net PnL, profit factor above 1.0, drawdown no worse than 15%, average round-trip execution cost no higher than 40 bps, and zero strategy-rule mismatches. Any strategy change restarts the paper sample.

## Simple Example

Historically, the primary changed $100 into $108.33. Under conservative costs it changed $100 into only $102.25, while the control lost money. This shows a small advantage that needs a live-data test.

The simple result is: **Stage 2 passed and the primary may move to simulated paper trading. Do not use real money yet. Paper trading must show that the small historical advantage survives real signals, latency, and execution costs.**
"""

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "REPORT.md").write_text(report)
    (OUTPUT / "decision.json").write_text(json.dumps(decision, indent=2) + "\n")
    manifest_paths = [STRATEGY, PERFORMANCE, COMPARISON, STRICT, *VALIDATIONS]
    manifest = {str(path.relative_to(ROOT)): sha256(path) for path in manifest_paths}
    (OUTPUT / "source_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    validation = {
        "step": "stage2_step12_final_report",
        "status": "PASS",
        "source_validations_passed": len(statuses),
        "primary_positive_baseline": True,
        "primary_positive_conservative_earlier": True,
        "primary_positive_conservative_later": True,
        "primary_beats_control_comparisons": int(sum(advantages)),
        "paper_trading_decision": decision["paper_trading_decision"],
        "real_money_decision": decision["real_money_decision"],
    }
    (OUTPUT / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()
