"""ETH experiment: freeze new-position size monthly from marked strategy equity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .confirmation_quality import quality
from .engine import CandidateTrade, MarketData, PortfolioConfig, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_monthly_compounding_v1.json"
CONTROL = "fixed_100_control"


def marked_equity_at(
    boundary_index: int, taken: list[dict], market: MarketData, config: PortfolioConfig,
) -> float:
    equity = float(config.initial_capital)
    for lot in taken:
        if int(lot["entry_index"]) >= boundary_index:
            continue
        if int(lot["exit_index"]) < boundary_index:
            equity += float(lot["pnl"])
        else:
            marked = (float(lot["quantity"]) * float(market.close[boundary_index])
                      * (1 - config.slippage_per_side) * (1 - config.fee_per_side))
            equity += marked - float(lot["spend"])
    return equity


def monthly_equity_sizer(
    market: MarketData, config: PortfolioConfig, equity_fraction: float,
    minimum_order: float, maximum_order: float, profit_only: bool,
):
    schedule: dict[str, dict[str, float]] = {}

    def size(candidate: CandidateTrade, taken: list[dict], _open_lots: list[dict]) -> float:
        timestamp = market.times[candidate.entry]
        month = timestamp.strftime("%Y-%m")
        if month not in schedule:
            boundary = timestamp.floor("D").replace(day=1)
            boundary_index = int(market.times.searchsorted(boundary))
            equity = marked_equity_at(boundary_index, taken, market, config)
            target = equity_fraction * equity
            if profit_only:
                target = max(config.lot_size, target)
            target = min(maximum_order, max(minimum_order, target))
            schedule[month] = {"month_start_equity": equity, "target_order_usd": target}
        return schedule[month]["target_order_usd"]

    size.schedule = schedule  # type: ignore[attr-defined]
    return size


def _ratio(result: ReplayResult) -> float:
    drawdown = abs(float(result.summary["maximum_drawdown_usd"]))
    return float(result.summary["net_profit"]) / drawdown if drawdown else float("inf")


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    threshold = 0.25

    results: dict[str, dict[str, ReplayResult]] = {
        CONTROL: {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}
    }
    monthly_rows = []
    for variant in experiment["variants"]:
        label = variant["name"]
        results[label] = {}
        for name in names:
            sizer = monthly_equity_sizer(
                market, portfolio, float(variant["equity_fraction"]),
                float(variant["minimum_order_usd"]), float(variant["maximum_order_usd"]),
                bool(variant["profit_only"]),
            )
            results[label][name] = replay_portfolio(
                candidates, market, *windows[name], portfolio, contextual_lot_sizer=sizer,
            )
            if name == "full":
                monthly_rows.extend({"variant": label, "month": month, **values}
                                    for month, values in sizer.schedule.items())  # type: ignore[attr-defined]

    _assert_expected(results[CONTROL]["full"].summary, baseline_config["acceptance"],
                     float(baseline_config["acceptance_tolerance"]))
    control = results[CONTROL]["full"]
    control_quality = quality(control, threshold)
    control_wf = sum(results[CONTROL][name].summary["net_profit"] for name in wf_names)
    acceptance = experiment["acceptance"]
    rows, window_rows = [], []
    for label, by_window in results.items():
        full = by_window["full"]
        q = quality(full, threshold)
        wf = sum(by_window[name].summary["net_profit"] for name in wf_names)
        changes = [by_window[name].summary["net_profit"] - results[CONTROL][name].summary["net_profit"]
                   for name in wf_names]
        row = {
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - control.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - control.summary["trades"],
            "economic_win_rate_pct": q["economic_win_rate_pct"],
            "average_win": full.summary["average_win"], "average_loss": full.summary["average_loss"],
            "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "profit_to_drawdown": _ratio(full),
            "profit_to_drawdown_change": _ratio(full) - _ratio(control),
            "average_order_usd": float(full.trades.spend.mean()),
            "maximum_order_usd": float(full.trades.spend.max()),
            "total_deployed_usd": float(full.trades.spend.sum()),
            "walk_forward_profit": wf, "walk_forward_change": wf - control_wf,
            "walk_forward_windows_improved": sum(change > 0 for change in changes),
        }
        row["accepted"] = bool(
            label != CONTROL
            and row["profit_change"] > acceptance["full_profit_change_gt"]
            and row["walk_forward_change"] > acceptance["walk_forward_profit_change_gt"]
            and row["walk_forward_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
            and row["profit_to_drawdown_change"] > acceptance["profit_to_drawdown_improvement_gt"]
            and row["average_loss"] >= control.summary["average_loss"]
            and row["max_drawdown_pct"] >= control.summary["maximum_drawdown_pct"]
            and row["economic_win_rate_pct"] >= control_quality["economic_win_rate_pct"]
        )
        rows.append(row)
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": by_window[name].summary["net_profit"],
                "profit_change": by_window[name].summary["net_profit"]
                                 - results[CONTROL][name].summary["net_profit"],
            })
    frame = pd.DataFrame(rows)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(output / "monthly_sizes.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    (output / "summary.json").write_text(json.dumps({
        "accepted_variants": accepted, "decision": "accept" if accepted else "reject_all",
    }, indent=2) + "\n")
    (output / "REPORT.md").write_text(_report(frame))
    return output


def _report(frame: pd.DataFrame) -> str:
    rows = []
    for row in frame.itertuples():
        decision = "CONTROL" if row.variant == CONTROL else ("PASS" if row.accepted else "FAIL")
        rows.append(
            f"| {row.variant} | ${row.profit:.2f} | ${row.profit_change:+.2f} | {row.trades} | "
            f"${row.average_order_usd:.2f} | ${row.average_win:.2f} | ${row.average_loss:.2f} | "
            f"{row.max_drawdown_pct:.2f}% | {row.profit_to_drawdown:.2f} | "
            f"${row.walk_forward_change:+.2f} | {row.walk_forward_windows_improved}/6 | {decision} |"
        )
    accepted = frame.loc[frame.accepted, "variant"].tolist()
    decision = f"Advance {', '.join(accepted)}." if accepted else "Reject both monthly compounding schedules."
    return f"""# ETH monthly controlled-compounding experiment

## Result

**{decision}**

| Sizing | Profit | vs base | Trades | Avg order | Avg win | Avg loss | Drawdown | Profit/drawdown | WF change | WF improved | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Sizes are frozen once per UTC month from marked strategy equity. Existing positions are never resized, and cash remains a hard limit.
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
