"""ETH experiment: resize each new position to one fifth of current marked equity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, MarketData, PortfolioConfig, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_continuous_compounding_v1.json"


def marked_equity_at_entry(candidate: CandidateTrade, taken: list[dict], market: MarketData,
                           config: PortfolioConfig) -> float:
    """Account equity known at an entry: closed P&L plus open lots at that minute's close."""
    equity = float(config.initial_capital)
    for lot in taken:
        if int(lot["entry_index"]) >= candidate.entry:
            continue
        if int(lot["exit_index"]) <= candidate.entry:
            equity += float(lot["pnl"])
        else:
            marked_value = (float(lot["quantity"]) * float(market.close[candidate.entry])
                            * (1 - config.slippage_per_side) * (1 - config.fee_per_side))
            equity += marked_value - float(lot["spend"])
    return equity


def continuous_equity_sizer(market: MarketData, config: PortfolioConfig):
    """Return a causal sizer; the engine remains responsible for cash and slot limits."""
    def size(candidate: CandidateTrade, taken: list[dict], _open_lots: list[dict]) -> float:
        return marked_equity_at_entry(candidate, taken, market, config) / config.maximum_lots
    return size


def _row(name: str, result) -> dict:
    trades = result.trades
    return {
        "sizing": name,
        "profit": result.summary["net_profit"],
        "ending_equity": result.summary["ending_equity"],
        "return_pct": result.summary["return_pct"],
        "trades": result.summary["trades"],
        "average_order": float(trades.spend.mean()) if len(trades) else 0.0,
        "minimum_order": float(trades.spend.min()) if len(trades) else 0.0,
        "maximum_order": float(trades.spend.max()) if len(trades) else 0.0,
        "average_win": result.summary["average_win"],
        "average_loss": result.summary["average_loss"],
        "drawdown_pct": result.summary["maximum_drawdown_pct"],
        "drawdown_usd": result.summary["maximum_drawdown_usd"],
        "profit_factor": result.summary["profit_factor"],
    }


def _markdown(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in frame.itertuples(index=False):
        values = []
        for value in row:
            values.append(f"{value:.4f}" if isinstance(value, float) else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    base_config = json.loads(DEFAULT_CONFIG.read_text())
    market, candidates, windows = baseline_module.build_baseline()
    fixed = _portfolio_config(base_config)
    compounding = PortfolioConfig(
        initial_capital=float(experiment["portfolio"]["initial_capital_usd"]),
        lot_size=float(experiment["portfolio"]["initial_capital_usd"]) / int(experiment["portfolio"]["slots"]),
        maximum_lots=int(experiment["portfolio"]["slots"]),
        fee_per_side=float(experiment["costs"]["fee_bps_per_side"]) / 10_000,
        slippage_per_side=float(experiment["costs"]["slippage_bps_per_side"]) / 10_000,
        minimum_order_usd=float(experiment["portfolio"]["minimum_order_usd"]),
        mark_frequency_minutes=int(experiment["evaluation"]["mark_frequency_minutes"]),
    )
    fixed_results = {name: replay_portfolio(candidates, market, *window, fixed)
                     for name, window in windows.items()}
    compound_results = {name: replay_portfolio(
        candidates, market, *window, compounding,
        contextual_lot_sizer=continuous_equity_sizer(market, compounding),
    ) for name, window in windows.items()}

    control, compounded = fixed_results["full"], compound_results["full"]
    rows = pd.DataFrame([_row("fixed_$100_control", control), _row("continuous_20pct_equity", compounded)])
    changes = [compound_results[f"wf{i}_test"].summary["net_profit"]
               - fixed_results[f"wf{i}_test"].summary["net_profit"] for i in range(6)]
    report = f"""# ETH continuous-compounding replay

## Result

This is a local ETH-only sizing simulation. It does not modify the live bot or server.

{_markdown(rows)}

## What continuous compounding means here

Start with **$500** and five **$100** slots. Before each new entry, the simulator values all earlier closed trades and marks any open ETH positions at the entry minute's completed close. The new order is **20% of that equity**. Therefore a loss lowers later order sizes and a gain raises them. Open positions are never resized; available cash and five slots remain hard limits.

The compounded replay changed full-period profit by **${compounded.summary['net_profit'] - control.summary['net_profit']:.2f}** and ending equity by the same amount. It improved **{sum(change > 0 for change in changes)}/6** walk-forward windows (walk-forward combined change **${sum(changes):.2f}**).

This does not prove a better strategy: it changes risk exposure. Compare the higher/lower dollar drawdown and the profit-to-drawdown relationship before any live sizing change.
"""
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    rows.to_csv(output / "summary.csv", index=False)
    compounded.trades.to_csv(output / "compounded_trades.csv", index=False)
    compounded.equity.to_csv(output / "compounded_equity_hourly.csv", index=False)
    pd.DataFrame([{"window": name, "fixed_profit": fixed_results[name].summary["net_profit"],
                   "compounded_profit": compound_results[name].summary["net_profit"],
                   "change": compound_results[name].summary["net_profit"] - fixed_results[name].summary["net_profit"]}
                  for name in windows]).to_csv(output / "windows.csv", index=False)
    (output / "REPORT.md").write_text(report)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = pd.read_csv(output / "summary.csv")
    print(summary.to_string(index=False))
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
