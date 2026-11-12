"""Experiment 6: replace the cosmetic binary win rate with economic trade classes."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_trade_quality_v1.json"


def classify_returns(returns_pct: pd.Series, threshold_pct: float) -> pd.Series:
    """Classify net returns without changing their exact P&L contribution."""
    return pd.Series(
        np.select(
            [returns_pct > threshold_pct, returns_pct < -threshold_pct],
            ["winner", "loser"], default="flat",
        ), index=returns_pct.index, name="economic_class",
    )


def metrics(trades: pd.DataFrame, threshold_pct: float, tail_fraction_pct: float) -> tuple[dict, pd.DataFrame]:
    ledger = trades.copy()
    ledger["net_return_pct"] = 100 * ledger.pnl / ledger.spend
    ledger["economic_class"] = classify_returns(ledger.net_return_pct, threshold_pct)
    counts = ledger.economic_class.value_counts()
    original_wins = int((ledger.pnl > 0).sum())
    original_losses = int((ledger.pnl <= 0).sum())
    gross_win = float(ledger.loc[ledger.pnl > 0, "pnl"].sum())
    gross_loss = float(-ledger.loc[ledger.pnl < 0, "pnl"].sum())
    armed = ledger.arm_index.notna()
    unarmed = ~armed
    floor_exits = ledger.exit_kind.eq("break_even")
    other_flats = ledger.economic_class.eq("flat") & ~floor_exits
    top_count = max(1, math.ceil(len(ledger) * tail_fraction_pct / 100))
    top_profit = float(ledger.nlargest(top_count, "pnl").pnl.sum())
    total_profit = float(ledger.pnl.sum())
    result = {
        "trades": int(len(ledger)), "net_profit": total_profit,
        "original_winners": original_wins, "original_losses": original_losses,
        "original_win_rate_pct": 100 * original_wins / len(ledger),
        "economic_winners": int(counts.get("winner", 0)),
        "economic_flats": int(counts.get("flat", 0)),
        "economic_losers": int(counts.get("loser", 0)),
        "floor_exits": int(floor_exits.sum()),
        "floor_exit_profit_usd": float(ledger.loc[floor_exits, "pnl"].sum()),
        "other_flat_trades": int(other_flats.sum()),
        "other_flat_profit_usd": float(ledger.loc[other_flats, "pnl"].sum()),
        "economic_win_rate_pct": 100 * counts.get("winner", 0) / len(ledger),
        "economic_flat_rate_pct": 100 * counts.get("flat", 0) / len(ledger),
        "economic_loss_rate_pct": 100 * counts.get("loser", 0) / len(ledger),
        "headline_win_rate_change_points": 100 * (counts.get("winner", 0) - original_wins) / len(ledger),
        "expectancy_usd_per_trade": float(ledger.pnl.mean()),
        "expectancy_pct_per_trade": float(ledger.net_return_pct.mean()),
        "profit_factor": gross_win / gross_loss if gross_loss else None,
        "median_trade_usd": float(ledger.pnl.median()),
        "median_trade_pct": float(ledger.net_return_pct.median()),
        "original_average_win_usd": float(ledger.loc[ledger.pnl > 0, "pnl"].mean()),
        "economic_average_win_usd": float(ledger.loc[ledger.economic_class == "winner", "pnl"].mean()),
        "average_loss_usd": float(ledger.loc[ledger.economic_class == "loser", "pnl"].mean()),
        "tail_trade_count": top_count, "tail_profit_usd": top_profit,
        "tail_contribution_pct": 100 * top_profit / total_profit if total_profit else np.nan,
        "profit_without_top_tail_usd": total_profit - top_profit,
        "armed_trades": int(armed.sum()), "armed_rate_pct": 100 * armed.mean(),
        "unarmed_trades": int(unarmed.sum()),
        "unarmed_protective_stops": int((unarmed & ledger.exit_kind.eq("protective_stop")).sum()),
        "stop_rate_among_unarmed_pct": (
            100 * (unarmed & ledger.exit_kind.eq("protective_stop")).sum() / unarmed.sum()
            if unarmed.sum() else 0.0
        ),
    }
    return result, ledger


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    market, candidates, windows = baseline_module.build_baseline()
    result = replay_portfolio(candidates, market, *windows["full"], _portfolio_config(baseline_config))
    threshold = float(experiment["classification"]["winner_above_net_return_pct"])
    tail_fraction = float(experiment["tail_definition"]["top_trade_fraction_pct"])
    summary, ledger = metrics(result.trades, threshold, tail_fraction)

    by_source = []
    for source, part in ledger.groupby("source", sort=True):
        source_summary, _ = metrics(part, threshold, tail_fraction)
        by_source.append({"source": source, **source_summary})

    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(output / "classified_trades.csv", index=False)
    pd.DataFrame(by_source).to_csv(output / "trade_quality_by_source.csv", index=False)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(summary, threshold, tail_fraction))
    return output


def _report(s: dict, threshold: float, tail_fraction: float) -> str:
    return f"""# ETH economic trade-quality report

## Result: SAME STRATEGY, MORE HONEST WIN RATE

This experiment changes reporting only. Entries, exits, trade count, fees and exact P&L are unchanged.

| Metric | Original baseline | Economic classification | Change |
|---|---:|---:|---:|
| Net profit | ${s['net_profit']:.2f} | ${s['net_profit']:.2f} | $0.00 |
| Trades | {s['trades']} | {s['trades']} | 0 |
| Reported winners | {s['original_winners']} | {s['economic_winners']} | {s['economic_winners'] - s['original_winners']:+d} |
| Win rate | {s['original_win_rate_pct']:.1f}% | {s['economic_win_rate_pct']:.1f}% | {s['headline_win_rate_change_points']:.1f} points |
| Average loss | ${s['average_loss_usd']:.2f} | ${s['average_loss_usd']:.2f} | $0.00 |

Economic classes use net return after costs: winner above +{threshold:.2f}%, flat from -{threshold:.2f}% through +{threshold:.2f}%, and loser below -{threshold:.2f}%.

| Class | Trades | Share |
|---|---:|---:|
| Winner | {s['economic_winners']} | {s['economic_win_rate_pct']:.1f}% |
| Floor exit | {s['floor_exits']} | {100 * s['floor_exits'] / s['trades']:.1f}% |
| Other flat | {s['other_flat_trades']} | {100 * s['other_flat_trades'] / s['trades']:.1f}% |
| Loser | {s['economic_losers']} | {s['economic_loss_rate_pct']:.1f}% |

## Economic quality

- Expectancy: **${s['expectancy_usd_per_trade']:.2f} per trade** ({s['expectancy_pct_per_trade']:.2f}%).
- Profit factor: **{s['profit_factor']:.2f}**.
- Median trade: **${s['median_trade_usd']:.2f}** ({s['median_trade_pct']:.2f}%).
- Average economic winner: **${s['economic_average_win_usd']:.2f}**.
- Average loser: **${s['average_loss_usd']:.2f}**.
- Floor exits: **{s['floor_exits']} trades**, **${s['floor_exit_profit_usd']:.2f} total**; these are not winners.
- Top {tail_fraction:.0f}% of trades: **${s['tail_profit_usd']:.2f}**, or **{s['tail_contribution_pct']:.1f}%** of total profit.
- Profit without those {s['tail_trade_count']} top trades: **${s['profit_without_top_tail_usd']:.2f}**.
- Reached the arm: **{s['armed_trades']}/{s['trades']} ({s['armed_rate_pct']:.1f}%)**.
- Protective-stop rate among unarmed trades: **{s['unarmed_protective_stops']}/{s['unarmed_trades']} ({s['stop_rate_among_unarmed_pct']:.1f}%)**.

## Decision

Use the three-class result as the primary win-rate report from now on. The strategy still earns the same ${s['net_profit']:.2f}, but **{s['original_win_rate_pct']:.1f}% should no longer be presented as the economic win rate**. The meaningful figure is {s['economic_win_rate_pct']:.1f}% winners, with {s['economic_flat_rate_pct']:.1f}% flat trades reported separately.
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
