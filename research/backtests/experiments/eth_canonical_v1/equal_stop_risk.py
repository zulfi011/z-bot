"""Experiment 15: size ETH lots by equal planned protective-stop risk."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, PortfolioConfig, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_equal_stop_risk_v1.json"


def equal_risk_sizer(stop_pct: dict[str, float], risk_usd: float, maximum_order_usd: float):
    def size(candidate: CandidateTrade) -> float:
        return min(float(maximum_order_usd), float(risk_usd) / (float(stop_pct[candidate.source]) / 100))
    return size


def gap_stress(candidates: list[CandidateTrade], extra_bps: float) -> list[CandidateTrade]:
    multiplier = 1 - float(extra_bps) / 10_000
    return [replace(candidate, exit_price=candidate.exit_price * multiplier)
            if candidate.exit_kind == "protective_stop" else candidate for candidate in candidates]


def _risk_metrics(result: ReplayResult, stop_pct: dict[str, float],
                  config: PortfolioConfig) -> dict:
    trades = result.trades.copy()
    trades["stop_pct"] = trades.source.map(stop_pct).astype(float)
    trades["planned_stop_risk"] = trades.spend * trades.stop_pct / 100
    stops = trades[trades.exit_kind == "protective_stop"].copy()
    if len(stops):
        stop_raw = stops.entry_fill_price * (1 - stops.stop_pct / 100)
        expected = (stops.quantity * stop_raw * (1 - config.slippage_per_side)
                    * (1 - config.fee_per_side))
        stops["gap_loss"] = (expected - stops.proceeds).clip(lower=0)
        actual = -stops.pnl
    else:
        stops["gap_loss"] = pd.Series(dtype=float)
        actual = pd.Series(dtype=float)
    return {
        "planned_risk_mean": float(trades.planned_stop_risk.mean()),
        "protective_stops": len(stops),
        "protective_stop_average_loss": float(actual.mean()) if len(actual) else 0.0,
        "protective_stop_worst_loss": float(actual.max()) if len(actual) else 0.0,
        "historical_gap_loss_total": float(stops.gap_loss.sum()),
        "historical_gap_stops": int((stops.gap_loss > 1e-9).sum()),
        "maximum_single_gap_loss": float(stops.gap_loss.max()) if len(stops) else 0.0,
    }


def _source_sizes(result: ReplayResult, stop_pct: dict[str, float]) -> pd.DataFrame:
    trades = result.trades.copy()
    trades["planned_stop_risk"] = trades.spend * trades.source.map(stop_pct).astype(float) / 100
    return (trades.groupby("source", as_index=False)
            .agg(trades=("candidate_id", "count"), average_order_usd=("spend", "mean"),
                 minimum_order_usd=("spend", "min"), maximum_order_usd=("spend", "max"),
                 average_planned_stop_risk=("planned_stop_risk", "mean"), profit=("pnl", "sum")))


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio: PortfolioConfig = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    stop_pct = experiment["stop_pct"]
    baseline = {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}
    base_full = baseline["full"]
    rows, window_rows, size_rows, stress_rows, trade_rows = [], [], [], [], []

    schedules = {"fixed_100_control": None}
    for item in experiment["variants"]:
        schedules[item["name"]] = equal_risk_sizer(
            stop_pct, float(item["risk_usd"]), float(item["maximum_order_usd"])
        )

    all_results: dict[str, dict[str, ReplayResult]] = {}
    for label, sizer in schedules.items():
        results = {name: replay_portfolio(candidates, market, *windows[name], portfolio, lot_sizer=sizer)
                   for name in names}
        all_results[label] = results
        full = results["full"]
        changes = [results[name].summary["net_profit"] - baseline[name].summary["net_profit"]
                   for name in wf_names]
        rows.append({
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - base_full.summary["trades"],
            "win_rate_pct": full.summary["win_rate_pct"], "average_win": full.summary["average_win"],
            "average_loss": full.summary["average_loss"], "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_change": sum(changes), "wf_windows_improved": sum(change > 0 for change in changes),
            **_risk_metrics(full, stop_pct, portfolio),
        })
        size_rows.append(_source_sizes(full, stop_pct).assign(variant=label))
        trade_rows.append(full.trades.assign(variant=label))
        for name in names:
            window_rows.append({"variant": label, "window": name,
                                "profit": results[name].summary["net_profit"],
                                "baseline_profit": baseline[name].summary["net_profit"],
                                "profit_change": results[name].summary["net_profit"] - baseline[name].summary["net_profit"]})

    for label, sizer in schedules.items():
        for extra_bps in experiment["stress_extra_stop_gap_bps"]:
            stressed = replay_portfolio(gap_stress(candidates, extra_bps), market, *windows["full"],
                                        portfolio, lot_sizer=sizer)
            unstressed = all_results[label]["full"]
            stress_rows.append({
                "variant": label, "extra_stop_gap_bps": extra_bps,
                "profit": stressed.summary["net_profit"],
                "profit_change_from_own_unstressed": (stressed.summary["net_profit"]
                                                       - unstressed.summary["net_profit"]),
                "max_drawdown_pct": stressed.summary["maximum_drawdown_pct"],
            })

    frame = pd.DataFrame(rows).sort_values("profit", ascending=False)
    sizes = pd.concat(size_rows, ignore_index=True)
    stress = pd.DataFrame(stress_rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "sizing_results.csv", index=False)
    sizes.to_csv(output / "source_order_sizes.csv", index=False)
    stress.to_csv(output / "gap_stress.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    baseline_summary = {**base_full.summary, **_risk_metrics(base_full, stop_pct, portfolio)}
    (output / "summary.json").write_text(json.dumps({
        "baseline": baseline_summary, "best_full_profit": frame.iloc[0].to_dict(),
        "best_drawdown": frame.sort_values("max_drawdown_pct", ascending=False).iloc[0].to_dict(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(baseline_summary, frame, sizes, stress))
    return output


def _report(base: dict, frame: pd.DataFrame, sizes: pd.DataFrame, stress: pd.DataFrame) -> str:
    rows = "\n".join(
        f"| {row.variant}{' (control)' if row.variant == 'fixed_100_control' else ''} | "
        f"${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | "
        f"{row.win_rate_pct:.1f}% | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
        f"{row.max_drawdown_pct:.2f}% | ${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 | "
        f"${row.protective_stop_average_loss:.2f} | ${row.historical_gap_loss_total:.2f} |"
        for row in frame.itertuples()
    )
    size_rows = "\n".join(
        f"| {row.variant} | {row.source} | ${row.average_order_usd:.2f} | "
        f"${row.average_planned_stop_risk:.2f} | ${row.profit:.2f} |" for row in sizes.itertuples()
    )
    stress_rows = "\n".join(
        f"| {row.variant} | +{row.extra_stop_gap_bps:.0f} bps | ${row.profit:.2f} | "
        f"${row.profit_change_from_own_unstressed:+.2f} | {row.max_drawdown_pct:.2f}% |"
        for row in stress.itertuples()
    )
    candidates = frame[frame.variant != "fixed_100_control"]
    best = candidates.iloc[0]
    passed = bool(best.profit_change > 0 and best.walk_forward_change > 0
                  and best.wf_windows_improved >= 4
                  and best.max_drawdown_pct >= base["maximum_drawdown_pct"])
    return f"""# ETH equal-planned-stop-risk sizing experiment

## Original fixed-$100 baseline

**${base['net_profit']:.2f} profit · {base['trades']} trades · {base['win_rate_pct']:.1f}% headline wins · ${base['average_loss']:.2f} average loss · {base['maximum_drawdown_pct']:.2f}% drawdown**

## Same $500 cash, no leverage or borrowing

| Sizing | Profit | Change | Trades | Win rate | Avg win | Avg loss | Drawdown | WF change | WF improved | Avg protective loss | Historical gap loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

## Actual order allocation

| Sizing | Entry family | Average order | Average planned stop risk | Profit contribution |
|---|---|---:|---:|---:|
{size_rows}

Orders can be smaller than their target when the shared cash wallet is partly occupied. They can never exceed available cash.

## Extra gap-through-stop stress

| Sizing | Additional adverse stop gap | Profit | Change from own unstressed result | Drawdown |
|---|---:|---:|---:|---:|
{stress_rows}

## Decision

{"**Advance `" + str(best.variant) + "` to forward testing, but do not deploy yet.**" if passed else "**Keep fixed $100 orders.** No equal-risk schedule passed the frozen profit, walk-forward consistency and drawdown gates."}

Historical stop exits already use the worse of the stop level and the next tradable open. The separate +25/+50 bps cases show how every protective stop behaves under additional adverse execution.
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
