"""Experiment 16: recalibrate ETH against observed live execution costs when observations exist."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, MarketData, PortfolioConfig, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_execution_calibration_v1.json"
TEMPLATE_COLUMNS = [
    "symbol", "side", "status", "decision_at", "best_bid", "best_ask", "expected_next_open",
    "actual_average_fill", "order_latency_ms", "fee_asset", "fee_rate_bps", "price_impact_bps",
    "next_open_slippage_bps", "client_order_id", "exchange_order_id", "recovered_retry", "rejection_reason",
]


def observed_scenarios(path: Path, minimum: int) -> tuple[list[dict], dict]:
    if not path.exists():
        return [], {"status": "missing", "fills": 0, "reason": f"No observation export at {path}"}
    frame = pd.read_csv(path)
    missing = set(TEMPLATE_COLUMNS) - set(frame.columns)
    if missing:
        return [], {"status": "invalid", "fills": 0, "reason": f"Missing columns: {sorted(missing)}"}
    fills = frame[(frame.symbol == "ETHUSDT") & frame.status.isin(["filled", "filled_stop"])].copy()
    fills["fee_rate_bps"] = pd.to_numeric(fills.fee_rate_bps, errors="coerce")
    fills["next_open_slippage_bps"] = pd.to_numeric(fills.next_open_slippage_bps, errors="coerce")
    usable = fills.dropna(subset=["fee_rate_bps", "next_open_slippage_bps"])
    if len(usable) < minimum:
        return [], {"status": "insufficient", "fills": len(usable),
                    "reason": f"Need {minimum} complete real ETH fills; found {len(usable)}"}
    adverse = usable.next_open_slippage_bps.clip(lower=0)
    scenarios = []
    for name, quantile in (("observed_median", 0.5), ("observed_p90", 0.9), ("observed_worst", 1.0)):
        scenarios.append({
            "name": name,
            "fee_bps_per_side": float(usable.fee_rate_bps.quantile(quantile)),
            "slippage_bps_per_side": float(adverse.quantile(quantile)),
        })
    return scenarios, {
        "status": "ready", "fills": len(usable),
        "rejected_orders": int((frame.status == "rejected").sum()),
        "recovered_retries": int(frame.recovered_retry.fillna(False).astype(bool).sum()),
        "median_latency_ms": float(pd.to_numeric(usable.order_latency_ms, errors="coerce").median()),
        "p90_latency_ms": float(pd.to_numeric(usable.order_latency_ms, errors="coerce").quantile(0.9)),
    }


def build_for_costs(fee_bps: float, slippage_bps: float) -> tuple[MarketData, list[CandidateTrade], dict]:
    """Rebuild exits and the armed floor, rather than merely subtracting extra costs afterward."""
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    baseline_module.grid.SLIP = float(slippage_bps) / 10_000
    rule = baseline_module.live.load_rule("eth")
    line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    prior_costs = baseline_module.floor_arm.COSTS
    round_trip_cost_pct = 2 * (float(fee_bps) + float(slippage_bps)) / 100
    baseline_module.floor_arm.COSTS = round_trip_cost_pct
    baseline_module.floor_arm.LINE_FLOOR = line * (1 + round_trip_cost_pct / 100)
    try:
        sources = (
            (baseline_module.live.live_entries(raw, rule), "dip", baseline_module.modes.DIP_STOP,
             rule["activation_pct"], rule["giveback_pct"]),
            ([trade["entry"] for trade in baseline_module.compare.mode_c(
                raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5
            )], "breakout", 3.5, 1.283, 22.0),
            (baseline_module.pullback.pullback_entries(
                baseline_module.grid.CLOSE, bullish, 24, 180, baseline_module.grid.TIMES, blocked=rule["blocked"]
            ), "pullback", baseline_module.modes.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
        )
        book = baseline_module.floor_arm.book(
            sources, bullish, line, baseline_module.floor_arm.DEPLOYED_ARM, "buy price", "on arming"
        )
        candidates = [CandidateTrade(
            entry=int(trade["entry"]), exit=int(trade["exit"]), exit_price=float(trade["price"]),
            source=str(trade["source"]), exit_code=int(trade["why"]),
            candidate_id=f"{trade['source']}:{baseline_module.grid.TIMES[int(trade['entry'])].isoformat()}:{index}",
            exit_kind=baseline_module._exit_kind(trade), arm_index=baseline_module._arm_index(trade),
            bullish_entry=bool(bullish[int(trade["entry"])]),
        ) for index, trade in enumerate(book)]
    finally:
        baseline_module.floor_arm.COSTS = prior_costs
    market = MarketData(pd.DatetimeIndex(baseline_module.grid.TIMES),
                        baseline_module.grid.OPEN.copy(), baseline_module.grid.CLOSE.copy())
    windows = dict(baseline_module.research.WINDOWS)
    windows["post_selection_2026_08_09"] = windows.pop("unseen")
    return market, candidates, windows


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None,
        observations: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    base_portfolio = _portfolio_config(baseline_config)
    observation_path = observations or STAGE2_ROOT / experiment["observations_csv"]
    scenarios, observation_status = observed_scenarios(observation_path, experiment["minimum_observed_fills"])
    scenario_kind = "observed" if scenarios else "provisional"
    scenarios = scenarios or experiment["provisional_sensitivity"]
    rows = []
    for scenario in scenarios:
        fee, slip = float(scenario["fee_bps_per_side"]), float(scenario["slippage_bps_per_side"])
        market, candidates, windows = build_for_costs(fee, slip)
        portfolio = PortfolioConfig(
            initial_capital=base_portfolio.initial_capital, lot_size=base_portfolio.lot_size,
            maximum_lots=base_portfolio.maximum_lots, fee_per_side=fee / 10_000,
            slippage_per_side=slip / 10_000, minimum_order_usd=base_portfolio.minimum_order_usd,
            mark_frequency_minutes=base_portfolio.mark_frequency_minutes,
        )
        result = replay_portfolio(candidates, market, *windows["full"], portfolio)
        rows.append({"scenario": scenario["name"], "kind": scenario_kind,
                     "fee_bps_per_side": fee, "slippage_bps_per_side": slip,
                     "round_trip_cost_bps": 2 * (fee + slip), **result.summary})
    frame = pd.DataFrame(rows)
    control_profit = float(frame.iloc[0].net_profit)
    frame["profit_change_from_first_scenario"] = frame.net_profit - control_profit
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "cost_sensitivity.csv", index=False)
    if not observation_path.exists():
        observation_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=TEMPLATE_COLUMNS).to_csv(observation_path, index=False)
    (output / "observation_status.json").write_text(json.dumps(observation_status, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps({"observation_status": observation_status,
                                                       "scenario_kind": scenario_kind,
                                                       "scenarios": rows}, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(observation_status, scenario_kind, frame))
    return output


def _report(status: dict, kind: str, frame: pd.DataFrame) -> str:
    rows = "\n".join(
        f"| {row.scenario} | {row.kind} | {row.fee_bps_per_side:.2f} | {row.slippage_bps_per_side:.2f} | "
        f"{row.round_trip_cost_bps:.1f} | ${row.net_profit:.2f} | "
        f"${row.profit_change_from_first_scenario:+.2f} | ${row.average_loss:.2f} | "
        f"{row.maximum_drawdown_pct:.2f}% |" for row in frame.itertuples()
    )
    ready = kind == "observed"
    availability = ("The supplied export contains enough complete real ETH fills."
                    if ready else "No usable local export of real Lightsail ETH fills is available yet.")
    return f"""# ETH live-execution calibration

## Observation status

**{status['status'].upper()} — {status['reason'] if 'reason' in status else str(status['fills']) + ' complete ETH fills'}**

{availability} Therefore the table below is **provisional sensitivity**, not an observed median, p90 or worst result. The runner will automatically replace it with observed percentiles after at least 30 complete ETH fills are exported.

## Cost recalculation

| Scenario | Evidence | Fee/side bps | Slippage/side bps | Round trip bps | Profit | Change | Avg loss | Drawdown |
|---|---|---:|---:|---:|---:|---:|---:|---:|
{rows}

Every row rebuilds the break-even floor from that scenario's fee and slippage, then replays the same five-slot ETH strategy with full window-end truncation.

## Decision

{"**Observed calibration is ready for use.**" if ready else "**No live strategy conclusion yet.** Deploy the telemetry migration/code separately when approved, collect at least 30 real ETH fills, export them, and rerun this experiment."}

Do not describe the provisional 5/10/20 bps cases as measured live execution.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--observations", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output, args.observations)
    print((output / "REPORT.md").read_text())
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
