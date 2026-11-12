"""Replay the user's manual upward lot-size ratchet using one shared ETH cash pot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .continuous_compounding import marked_equity_at_entry
from .engine import CandidateTrade, MarketData, PortfolioConfig, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_manual_ratchet_compounding_v1.json"


def manual_ratchet_sizer(market: MarketData, config: PortfolioConfig, *, initial_lot: float,
                          profit_step: float, lot_increase: float):
    """Raise the configured lot permanently at $100 marked-equity profit milestones.

    The replay engine then applies ``min(configured_lot, free_cash)``.  That is the
    live shared-pot behaviour: early lots receive the configured amount and a later
    lot can receive the smaller cash balance left by previous closed losses.
    """
    high_water = float(config.initial_capital)
    applied_steps = 0
    changes: list[dict] = []
    decisions: list[dict] = []

    def size(candidate: CandidateTrade, taken: list[dict], _open_lots: list[dict]) -> float:
        nonlocal high_water, applied_steps
        equity = marked_equity_at_entry(candidate, taken, market, config)
        high_water = max(high_water, equity)
        steps = max(0, int((high_water - config.initial_capital + 1e-9) // profit_step))
        if steps > applied_steps:
            for step in range(applied_steps + 1, steps + 1):
                changes.append({
                    "entry_time": market.times[candidate.entry],
                    "profit_milestone_usd": step * profit_step,
                    "marked_equity_usd": equity,
                    "configured_lot_usd": initial_lot + step * lot_increase,
                })
            applied_steps = steps
        configured_lot = initial_lot + applied_steps * lot_increase
        decisions.append({
            "candidate_id": candidate.candidate_id,
            "entry_time": market.times[candidate.entry],
            "marked_equity_usd": equity,
            "configured_lot_usd": configured_lot,
        })
        return configured_lot

    size.changes = changes  # type: ignore[attr-defined]
    size.decisions = decisions  # type: ignore[attr-defined]
    return size


def _metrics(name: str, result) -> dict:
    trades = result.trades
    profit_to_dd = (result.summary["net_profit"] / abs(result.summary["maximum_drawdown_usd"])
                    if result.summary["maximum_drawdown_usd"] else float("inf"))
    return {
        "sizing": name,
        "profit": result.summary["net_profit"],
        "ending_equity": result.summary["ending_equity"],
        "return_pct": result.summary["return_pct"],
        "trades": result.summary["trades"],
        "average_order": float(trades.spend.mean()) if len(trades) else 0.0,
        "minimum_order": float(trades.spend.min()) if len(trades) else 0.0,
        "maximum_order": float(trades.spend.max()) if len(trades) else 0.0,
        "average_loss": result.summary["average_loss"],
        "drawdown_pct": result.summary["maximum_drawdown_pct"],
        "drawdown_usd": result.summary["maximum_drawdown_usd"],
        "profit_to_drawdown": profit_to_dd,
    }


def _markdown(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in frame.itertuples(index=False):
        lines.append("| " + " | ".join(
            f"{value:.4f}" if isinstance(value, float) else str(value) for value in row
        ) + " |")
    return "\n".join(lines)


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    base_config = json.loads(DEFAULT_CONFIG.read_text())
    market, candidates, windows = baseline_module.build_baseline()
    fixed = _portfolio_config(base_config)
    cfg = experiment["portfolio"]
    ratchet = PortfolioConfig(
        initial_capital=float(cfg["initial_capital_usd"]), lot_size=float(cfg["initial_lot_usd"]),
        maximum_lots=int(cfg["slots"]), minimum_order_usd=float(cfg["minimum_order_usd"]),
        fee_per_side=float(experiment["costs"]["fee_bps_per_side"]) / 10_000,
        slippage_per_side=float(experiment["costs"]["slippage_bps_per_side"]) / 10_000,
        mark_frequency_minutes=int(experiment["evaluation"]["mark_frequency_minutes"]),
    )

    fixed_results = {name: replay_portfolio(candidates, market, *window, fixed)
                     for name, window in windows.items()}
    ratchet_results, full_sizer = {}, None
    for name, window in windows.items():
        sizer = manual_ratchet_sizer(
            market, ratchet, initial_lot=float(cfg["initial_lot_usd"]),
            profit_step=float(cfg["profit_step_usd"]), lot_increase=float(cfg["lot_increase_per_step_usd"]),
        )
        ratchet_results[name] = replay_portfolio(
            candidates, market, *window, ratchet, contextual_lot_sizer=sizer,
        )
        if name == "full":
            full_sizer = sizer

    control, compounded = fixed_results["full"], ratchet_results["full"]
    summary = pd.DataFrame([_metrics("fixed_$100_control", control),
                            _metrics("manual_upward_ratchet", compounded)])
    window_rows = pd.DataFrame([
        {"window": name, "fixed_profit": fixed_results[name].summary["net_profit"],
         "ratchet_profit": ratchet_results[name].summary["net_profit"],
         "change": ratchet_results[name].summary["net_profit"] - fixed_results[name].summary["net_profit"]}
        for name in windows
    ])
    changes = window_rows[window_rows.window.str.startswith("wf") & window_rows.window.str.endswith("_test")]
    tiers = pd.DataFrame(full_sizer.changes if full_sizer is not None else [])
    decisions = pd.DataFrame(full_sizer.decisions if full_sizer is not None else [])
    trades_with_decisions = compounded.trades.merge(
        decisions[["candidate_id", "marked_equity_usd", "configured_lot_usd"]],
        on="candidate_id", how="left", validate="one_to_one",
    )
    trades_with_decisions["used_leftover_cash"] = (
        trades_with_decisions.spend + 1e-9 < trades_with_decisions.configured_lot_usd
    )
    partial = trades_with_decisions[trades_with_decisions.used_leftover_cash]
    report = f"""# ETH manual upward-ratchet compounding replay

## Result

{_markdown(summary)}

## Exact model tested

- Start with a **$500 ETH pot** and five **$100** configured lots.
- Once marked ETH-pot equity first reaches $600, the simulated manual setting becomes **5 × $120**. At $700 it becomes **5 × $140**, then continues in $100 / $20 steps.
- The configured size **never falls** after a loss.
- Each actual entry uses the lesser of that configured size and the actual free shared cash. Thus, after closed losses leave only $80 once four lots are funded, the fifth order is $80.
- Existing open lots are never resized. No leverage or borrowing is allowed.

The ratchet produced **${compounded.summary['net_profit'] - control.summary['net_profit']:.2f}** more full-period profit, improved **{int((changes.change > 0).sum())}/6** walk-forward test windows, and changed the combined walk-forward result by **${changes.change.sum():.2f}**.

There were **{len(partial)}** filled entries that used the smaller shared-cash remainder rather than the configured lot. Their smallest order was **${partial.spend.min() if len(partial) else 0:.2f}**.

This is a sizing comparison, not proof of a stronger entry/exit strategy. The key decision measure is whether the additional profit justifies the larger absolute drawdown.
"""
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output / "summary.csv", index=False)
    window_rows.to_csv(output / "windows.csv", index=False)
    trades_with_decisions.to_csv(output / "ratchet_trades.csv", index=False)
    compounded.equity.to_csv(output / "ratchet_equity_hourly.csv", index=False)
    tiers.to_csv(output / "ratchet_milestones.csv", index=False)
    (output / "REPORT.md").write_text(report)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    print(pd.read_csv(output / "summary.csv").to_string(index=False))
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
