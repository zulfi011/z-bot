"""ETH experiment: causally reduce lot size in high realized-volatility states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, ReplayResult, replay_portfolio
from .pullback_revalidation import _excluded_month_mask
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_volatility_sizing_v1.json"
CONTROL = "fixed_100_control"
NORMAL, HIGH, EXTREME = "normal", "high", "extreme"


def causal_volatility_states(close: np.ndarray, times: pd.DatetimeIndex, window_minutes: int = 1440,
                             reference_days: int = 90, high_quantile: float = 0.80,
                             extreme_quantile: float = 0.90) -> pd.DataFrame:
    """Classify each minute using no prices from that minute or later."""
    returns = pd.Series(np.log(np.asarray(close, dtype=float)), index=times).diff()
    squared = returns.pow(2)
    current = squared.rolling(window_minutes, min_periods=window_minutes).sum().pow(0.5).shift(1)

    day = times.floor("D")
    daily = pd.DataFrame({"squared": squared.to_numpy(), "day": day}).groupby("day").agg(
        squared=("squared", "sum"), observations=("squared", "count"),
    )
    # A UTC day needs 1,439 within-day changes plus the midnight change from the prior day.
    daily["rv"] = daily.squared.pow(0.5).where(daily.observations >= window_minutes - 1)
    prior = daily.rv.shift(1)
    q_high = prior.rolling(reference_days, min_periods=reference_days).quantile(high_quantile)
    q_extreme = prior.rolling(reference_days, min_periods=reference_days).quantile(extreme_quantile)
    high_at_minute = q_high.reindex(day).to_numpy()
    extreme_at_minute = q_extreme.reindex(day).to_numpy()
    rv = current.to_numpy()
    state = np.full(len(times), NORMAL, dtype=object)
    state[np.isfinite(high_at_minute) & (rv >= high_at_minute)] = HIGH
    state[np.isfinite(extreme_at_minute) & (rv >= extreme_at_minute)] = EXTREME
    return pd.DataFrame({
        "timestamp": times,
        "rv_24h": rv,
        "prior_90d_q80": high_at_minute,
        "prior_90d_q90": extreme_at_minute,
        "volatility_state": state,
    })


def order_size_for_state(state: str, schedule: dict) -> float:
    if state == EXTREME:
        return float(schedule["extreme_size_usd"])
    if state == HIGH:
        return float(schedule["high_size_usd"])
    return float(schedule["normal_size_usd"])


def volatility_sizer(states: np.ndarray, schedule: dict):
    def size(candidate: CandidateTrade) -> float:
        return order_size_for_state(str(states[candidate.entry]), schedule)
    return size


def _ratio(result: ReplayResult) -> float:
    loss = abs(float(result.summary["maximum_drawdown_usd"]))
    return float(result.summary["net_profit"]) / loss if loss else float("inf")


def _metrics(result: ReplayResult, states: np.ndarray, excluded_months: list[str],
             threshold: float) -> dict:
    trades = result.trades
    ordinary = trades[~_excluded_month_mask(trades, excluded_months)] if len(trades) else trades
    filled_states = states[trades.entry_index.to_numpy(dtype=int)] if len(trades) else np.array([], dtype=object)
    return {
        "profit": float(result.summary["net_profit"]),
        "trades": int(result.summary["trades"]),
        "headline_win_rate_pct": float(result.summary["win_rate_pct"]),
        "average_win": float(result.summary["average_win"]),
        "average_loss": float(result.summary["average_loss"]),
        "profit_factor": float(result.summary["profit_factor"]),
        "max_drawdown_pct": float(result.summary["maximum_drawdown_pct"]),
        "max_drawdown_usd": float(result.summary["maximum_drawdown_usd"]),
        "profit_to_drawdown": _ratio(result),
        "ordinary_profit": float(ordinary.pnl.sum()),
        "average_order_usd": float(trades.spend.mean()) if len(trades) else 0.0,
        "total_deployed_usd": float(trades.spend.sum()),
        "high_state_fills": int(np.sum(filled_states == HIGH)),
        "extreme_state_fills": int(np.sum(filled_states == EXTREME)),
        **quality(result, threshold),
    }


def _passes(row: dict, control: dict, acceptance: dict) -> bool:
    return bool(
        row["profit_retention_pct"] >= acceptance["minimum_full_profit_retention_pct"]
        and row["ordinary_profit_retention_pct"] >= acceptance["minimum_ordinary_profit_retention_pct"]
        and row["walk_forward_profit_retention_pct"] >= acceptance["minimum_walk_forward_profit_retention_pct"]
        and row["profit_to_drawdown_change"] > acceptance["profit_to_drawdown_improvement_gt"]
        and row["risk_adjusted_wf_windows_improved"]
            >= acceptance["minimum_risk_adjusted_walk_forward_windows_improved"]
        and row["average_loss"] >= control["average_loss"]
        and row["max_drawdown_pct"] >= control["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    volatility = experiment["volatility"]
    state_frame = causal_volatility_states(
        market.close, market.times,
        int(volatility["current_window_minutes"]), int(volatility["reference_days"]),
        float(volatility["high_percentile"]), float(volatility["extreme_percentile"]),
    )
    states = state_frame.volatility_state.to_numpy()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    schedules = {CONTROL: None, **{
        item["name"]: volatility_sizer(states, item) for item in experiment["variants"]
    }}
    results = {
        label: {name: replay_portfolio(
            candidates, market, *windows[name], portfolio, lot_sizer=sizer,
        ) for name in names}
        for label, sizer in schedules.items()
    }
    _assert_expected(
        results[CONTROL]["full"].summary, baseline_config["acceptance"],
        float(baseline_config["acceptance_tolerance"]),
    )
    excluded = experiment["excluded_entry_months"]
    threshold = float(experiment["economic_winner_threshold_pct"])
    control = _metrics(results[CONTROL]["full"], states, excluded, threshold)
    control_wf_profit = sum(results[CONTROL][name].summary["net_profit"] for name in wf_names)
    rows, window_rows, trade_rows = [], [], []
    for label, by_window in results.items():
        metrics = _metrics(by_window["full"], states, excluded, threshold)
        wf_profit = sum(by_window[name].summary["net_profit"] for name in wf_names)
        risk_changes = [_ratio(by_window[name]) - _ratio(results[CONTROL][name]) for name in wf_names]
        row = {
            "variant": label,
            **metrics,
            "profit_change": metrics["profit"] - control["profit"],
            "profit_retention_pct": 100 * metrics["profit"] / control["profit"],
            "ordinary_profit_change": metrics["ordinary_profit"] - control["ordinary_profit"],
            "ordinary_profit_retention_pct": 100 * metrics["ordinary_profit"] / control["ordinary_profit"],
            "drawdown_change_pct_points": metrics["max_drawdown_pct"] - control["max_drawdown_pct"],
            "profit_to_drawdown_change": metrics["profit_to_drawdown"] - control["profit_to_drawdown"],
            "walk_forward_profit": wf_profit,
            "walk_forward_change": wf_profit - control_wf_profit,
            "walk_forward_profit_retention_pct": 100 * wf_profit / control_wf_profit,
            "risk_adjusted_wf_windows_improved": sum(change > 0 for change in risk_changes),
        }
        row["accepted"] = label != CONTROL and _passes(row, control, experiment["acceptance"])
        rows.append(row)
        trade_rows.append(by_window["full"].trades.assign(
            variant=label,
            volatility_state=states[by_window["full"].trades.entry_index.to_numpy(dtype=int)],
        ))
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": by_window[name].summary["net_profit"],
                "control_profit": results[CONTROL][name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"]
                                 - results[CONTROL][name].summary["net_profit"],
                "profit_to_drawdown": _ratio(by_window[name]),
                "control_profit_to_drawdown": _ratio(results[CONTROL][name]),
                "profit_to_drawdown_change": _ratio(by_window[name]) - _ratio(results[CONTROL][name]),
            })

    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "sizing_results.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    state_frame.to_csv(output / "causal_volatility_states.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "control": frame[frame.variant == CONTROL].iloc[0].to_dict(),
        "accepted_variants": accepted,
        "decision": "accept" if accepted else "reject_all",
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    labels = {
        CONTROL: "Fixed $100 control",
        "high20_size70": "Top 20% → $70",
        "extreme10_size50": "Top 10% → $50",
        "tiered_70_50": "Top 20% → $70; top 10% → $50",
    }
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {labels[row.variant]} | ${row.profit:.2f} | ${row.profit_change:+.2f} | "
            f"{row.profit_retention_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | {row.profit_to_drawdown:.2f} | "
            f"${row.ordinary_profit_change:+.2f} | ${row.walk_forward_change:+.2f} | "
            f"{row.risk_adjusted_wf_windows_improved}/6 | ${row.average_order_usd:.2f} | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)} to untouched forward testing; do not deploy yet." if accepted else (
        "Reject all three sizing schedules; keep fixed $100 orders."
    )
    return f"""# ETH causal volatility-sizing experiment

## Result

**{decision}**

| Sizing | Profit | vs base | Profit retained | Avg win | Avg loss | Drawdown | Profit/drawdown | Ex-Apr/May change | WF change | Risk-adjusted WF improved | Avg order | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

All 459 signals and exits are unchanged. Current volatility uses the completed prior 24 hours; the 80th and 90th percentile thresholds use only the previous 90 completed UTC days. Smaller orders never create extra slots, leverage, or borrowing.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    print((output / "REPORT.md").read_text())
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
