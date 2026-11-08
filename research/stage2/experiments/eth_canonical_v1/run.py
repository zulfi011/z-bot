"""Run and verify the canonical ETH baseline, then write audit-friendly artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .baseline import STAGE2_ROOT, build_baseline
from .engine import PortfolioConfig, ReplayResult, replay_portfolio

DEFAULT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_canonical_v1.json"


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text())


def _portfolio_config(config: dict) -> PortfolioConfig:
    portfolio, costs = config["portfolio"], config["costs"]
    return PortfolioConfig(
        initial_capital=float(portfolio["initial_capital_usd"]),
        lot_size=float(portfolio["lot_size_usd"]),
        maximum_lots=int(portfolio["lots"]),
        fee_per_side=float(costs["fee_bps_per_side"]) / 10_000,
        slippage_per_side=float(costs["slippage_bps_per_side"]) / 10_000,
        minimum_order_usd=float(portfolio["minimum_order_usd"]),
        mark_frequency_minutes=int(config["evaluation"]["mark_frequency_minutes"]),
    )


def _assert_expected(actual: dict, expected: dict, tolerance: float) -> None:
    failures = []
    for key, target in expected.items():
        value = actual[key]
        if isinstance(target, int):
            if int(value) != target:
                failures.append(f"{key}: expected {target}, got {value}")
        elif abs(float(value) - float(target)) > tolerance:
            failures.append(f"{key}: expected {target}, got {value}")
    if failures:
        raise AssertionError("Baseline reproduction failed:\n" + "\n".join(failures))


def _source_rows(result: ReplayResult) -> list[dict]:
    rows = []
    for source, part in result.trades.groupby("source", sort=True):
        wins, losses = part[part.pnl > 0], part[part.pnl <= 0]
        rows.append({
            "source": source, "trades": len(part), "wins": len(wins),
            "win_rate_pct": 100 * len(wins) / len(part), "net_profit": part.pnl.sum(),
            "average_win": wins.pnl.mean() if len(wins) else 0.0,
            "average_loss": losses.pnl.mean() if len(losses) else 0.0,
        })
    return rows


def _markdown(frame: pd.DataFrame) -> str:
    """Small dependency-free Markdown table for the generated research report."""
    columns = list(frame.columns)

    def cell(value) -> str:
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value).replace("|", "\\|")

    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    lines.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in frame.itertuples(index=False))
    return "\n".join(lines)


def _report(config: dict, full: ReplayResult, windows: pd.DataFrame, sources: pd.DataFrame) -> str:
    s = full.summary
    return f"""# ETH canonical baseline v1

This is an ETH-only local research control. It does not connect to Binance, a server, or the live database.

## Acceptance

**PASS** — the canonical engine reproduced the frozen ETH-v5 control inside the configured tolerance.

| Metric | Result |
|---|---:|
| Trades | {s['trades']} |
| Won / lost | {s['wins']} / {s['losses']} |
| Win rate | {s['win_rate_pct']:.2f}% |
| Net profit | ${s['net_profit']:.4f} |
| Average win | ${s['average_win']:.4f} |
| Average loss | ${s['average_loss']:.4f} |
| Profit factor | {s['profit_factor']:.3f} |
| Hourly mark-to-market drawdown | {s['maximum_drawdown_pct']:.4f}% |
| Candidate signals | {s['candidate_count']} |
| Blocked candidates | {s['blocked_candidates']} |

## Entry-family contribution

{_markdown(sources)}

## Evaluation windows

{_markdown(windows)}

## Rules enforced by this engine

- Complete shared-wallet replay; no editing of an old trade ledger.
- Stable same-minute ordering.
- Trades are truncated and liquidated at the last completed minute of each evaluation window.
- Hourly mark-to-market equity includes unrealized P&L.
- Every candidate rejected for slot or cash constraints is logged.
- All future ETH experiments must compare against this unchanged control.

Configuration: `{config['experiment_id']}`.
"""


def run(config_path: Path = DEFAULT_CONFIG, output_dir: Path | None = None) -> Path:
    config = _load_config(config_path)
    if config.get("symbol") != "ETHUSDT":
        raise ValueError("The canonical v1 runner is intentionally restricted to ETHUSDT")
    market, candidates, definitions = build_baseline()
    portfolio = _portfolio_config(config)
    names = config["evaluation"]["windows"]
    results = {
        name: replay_portfolio(candidates, market, *definitions[name], portfolio)
        for name in names
    }
    full = results["full"]
    _assert_expected(full.summary, config["acceptance"], float(config["acceptance_tolerance"]))

    output = output_dir or STAGE2_ROOT / "results" / config["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    full.trades.to_csv(output / "baseline_trades.csv", index=False)
    full.blocked_signals.to_csv(output / "baseline_blocked_signals.csv", index=False)
    full.equity.to_csv(output / "baseline_equity_hourly.csv", index=False)
    (output / "baseline_summary.json").write_text(json.dumps(full.summary, indent=2, default=float) + "\n")

    window_rows = [{"window": name, **result.summary} for name, result in results.items()]
    windows = pd.DataFrame(window_rows)
    windows.to_csv(output / "baseline_windows.csv", index=False)
    sources = pd.DataFrame(_source_rows(full))
    sources.to_csv(output / "baseline_by_source.csv", index=False)
    (output / "REPORT.md").write_text(_report(config, full, windows, sources))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = json.loads((output / "baseline_summary.json").read_text())
    print(f"PASS: {summary['trades']} ETH trades, ${summary['net_profit']:.4f} profit, "
          f"{summary['maximum_drawdown_pct']:.4f}% max drawdown")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
