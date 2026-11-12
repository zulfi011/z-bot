"""Experiment 14: revalidate ETH blocked entry hours and select them walk-forward."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .engine import CandidateTrade, PortfolioConfig, ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_blocked_hours_v1.json"


def build_all_hours() -> tuple[object, list[CandidateTrade], dict]:
    """Build all three deployed ETH entry families without an entry-hour filter."""
    market, _, windows = baseline_module.build_baseline()
    raw, bullish = baseline_module.compare.load("ETHUSDT")
    rule = {**baseline_module.live.load_rule("eth"), "blocked": None}
    line = pd.Series(baseline_module.grid.CLOSE).ewm(span=16 * 60, adjust=False).mean().to_numpy()
    baseline_module.floor_arm.LINE_FLOOR = line * (1 + baseline_module.floor_arm.COSTS / 100)
    sources = (
        (baseline_module.live.live_entries(raw, rule), "dip", baseline_module.modes.DIP_STOP,
         rule["activation_pct"], rule["giveback_pct"]),
        ([trade["entry"] for trade in baseline_module.compare.mode_c(
            raw, rule, 120, 12, 2.5, 30, 1.283, 22.0, 3.5
        )], "breakout", 3.5, 1.283, 22.0),
        (baseline_module.pullback.pullback_entries(
            baseline_module.grid.CLOSE, bullish, 24, 180, baseline_module.grid.TIMES, blocked=None
        ), "pullback", baseline_module.modes.DIP_STOP, rule["activation_pct"], rule["giveback_pct"]),
    )
    book = baseline_module.floor_arm.book(
        sources, bullish, line, baseline_module.floor_arm.DEPLOYED_ARM, "buy price", "on arming"
    )
    candidates = [CandidateTrade(
        entry=int(trade["entry"]), exit=int(trade["exit"]), exit_price=float(trade["price"]),
        source=str(trade["source"]), exit_code=int(trade["why"]),
        candidate_id=f"all-hours:{trade['source']}:{baseline_module.grid.TIMES[int(trade['entry'])].isoformat()}:{index}",
        exit_kind=baseline_module._exit_kind(trade), arm_index=baseline_module._arm_index(trade),
        bullish_entry=bool(bullish[int(trade["entry"])]),
    ) for index, trade in enumerate(book)]
    return market, candidates, windows


def apply_block(candidates: list[CandidateTrade], market, block: list[int] | None) -> list[CandidateTrade]:
    if block is None:
        return candidates
    start, end = map(int, block)
    return [candidate for candidate in candidates
            if not start <= market.times[candidate.entry].hour < end]


def _quality(result: ReplayResult) -> dict:
    returns = 100 * result.trades.pnl / result.trades.spend
    return {
        "economic_win_rate_pct": 100 * float((returns > 0.25).mean()),
        "expectancy_per_trade": float(result.trades.pnl.mean()),
    }


def _entry_bucket(hour: int) -> str:
    start = (int(hour) // 6) * 6
    return f"{start:02d}-{start + 6:02d}"


def _hour_attribution(result: ReplayResult) -> pd.DataFrame:
    trades = result.trades.copy()
    trades["entry_hour_utc"] = trades.entry_time.dt.hour
    trades["six_hour_bucket"] = trades.entry_hour_utc.map(_entry_bucket)
    return (trades.groupby("six_hour_bucket", as_index=False)
            .agg(trades=("candidate_id", "count"), profit=("pnl", "sum"),
                 win_rate_pct=("pnl", lambda values: 100 * (values > 0).mean()),
                 average_pnl=("pnl", "mean"), average_loss=("pnl", lambda values: values[values <= 0].mean())))


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio: PortfolioConfig = _portfolio_config(baseline_config)
    market, all_candidates, windows = build_all_hours()
    choices = {label: apply_block(all_candidates, market, block)
               for label, block in experiment["choices"].items()}
    names = baseline_config["evaluation"]["windows"]
    wf_tests = [f"wf{index}_test" for index in range(6)]
    wf_trains = [f"wf{index}_train" for index in range(6)]
    evaluation_names = list(dict.fromkeys([*names, *wf_trains]))
    results = {label: {name: replay_portfolio(book, market, *windows[name], portfolio)
                       for name in evaluation_names} for label, book in choices.items()}
    control_label = experiment["deployed_choice"]
    control = results[control_label]
    base_full = control["full"]
    rows, window_rows, trade_rows = [], [], []
    for label, by_window in results.items():
        full = by_window["full"]
        changes = [by_window[name].summary["net_profit"] - control[name].summary["net_profit"]
                   for name in wf_tests]
        rows.append({
            "variant": label, "profit": full.summary["net_profit"],
            "profit_change": full.summary["net_profit"] - base_full.summary["net_profit"],
            "trades": full.summary["trades"], "trade_change": full.summary["trades"] - base_full.summary["trades"],
            "win_rate_pct": full.summary["win_rate_pct"], "average_win": full.summary["average_win"],
            "average_loss": full.summary["average_loss"], "profit_factor": full.summary["profit_factor"],
            "max_drawdown_pct": full.summary["maximum_drawdown_pct"],
            "walk_forward_profit": sum(by_window[name].summary["net_profit"] for name in wf_tests),
            "walk_forward_change": sum(changes), "wf_windows_improved": sum(change > 0 for change in changes),
            **_quality(full),
        })
        trade_rows.append(full.trades.assign(variant=label))
        for name in evaluation_names:
            window_rows.append({"variant": label, "window": name,
                                "profit": by_window[name].summary["net_profit"],
                                "trades": by_window[name].summary["trades"]})

    selections = []
    for index, (train, test) in enumerate(zip(wf_trains, wf_tests, strict=True)):
        chosen = max(choices, key=lambda label: (results[label][train].summary["net_profit"], label))
        selected_profit = results[chosen][test].summary["net_profit"]
        control_profit = control[test].summary["net_profit"]
        selections.append({
            "fold": index, "train_window": train, "test_window": test, "selected": chosen,
            "training_profit": results[chosen][train].summary["net_profit"],
            "test_profit": selected_profit, "control_test_profit": control_profit,
            "test_change": selected_profit - control_profit,
        })

    frame = pd.DataFrame(rows).sort_values("profit", ascending=False)
    selection_frame = pd.DataFrame(selections)
    all_hours_full = results["all_hours"]["full"]
    attribution = _hour_attribution(all_hours_full)
    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / "fixed_blocks.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    selection_frame.to_csv(output / "walk_forward_selection.csv", index=False)
    attribution.to_csv(output / "all_hours_entry_bucket_attribution.csv", index=False)
    pd.concat(trade_rows, ignore_index=True).to_csv(output / "variant_trades.csv", index=False)
    control_summary = {**base_full.summary, **_quality(base_full)}
    (output / "summary.json").write_text(json.dumps({
        "control": control_summary, "best_fixed_full": frame.iloc[0].to_dict(),
        "walk_forward_selection_profit": selection_frame.test_profit.sum(),
        "walk_forward_control_profit": selection_frame.control_test_profit.sum(),
        "walk_forward_selection_change": selection_frame.test_change.sum(),
    }, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(control_summary, frame, selection_frame, attribution))
    return output


def _report(base: dict, frame: pd.DataFrame, selection: pd.DataFrame,
            attribution: pd.DataFrame) -> str:
    rows = "\n".join(
        f"| {row.variant}{' (control)' if row.variant == 'block_06_12' else ''} | ${row.profit:.2f} | "
        f"${row.profit_change:+.2f} | {row.trades} ({row.trade_change:+d}) | {row.win_rate_pct:.1f}% | "
        f"{row.economic_win_rate_pct:.1f}% | ${row.average_loss:.2f} | {row.max_drawdown_pct:.2f}% | "
        f"${row.walk_forward_change:+.2f} | {row.wf_windows_improved}/6 |"
        for row in frame.itertuples()
    )
    selection_rows = "\n".join(
        f"| {row.test_window} | {row.selected} | ${row.training_profit:.2f} | ${row.test_profit:.2f} | "
        f"${row.control_test_profit:.2f} | ${row.test_change:+.2f} |" for row in selection.itertuples()
    )
    hour_rows = "\n".join(
        f"| {row.six_hour_bucket} | {row.trades} | ${row.profit:.2f} | {row.win_rate_pct:.1f}% | "
        f"${row.average_pnl:.2f} | ${row.average_loss:.2f} |" for row in attribution.itertuples()
    )
    chosen_counts = selection.selected.value_counts().to_dict()
    selection_profit = float(selection.test_profit.sum())
    control_profit = float(selection.control_test_profit.sum())
    return f"""# ETH blocked-entry-hours revalidation

## Original baseline

**${base['net_profit']:.2f} profit · {base['trades']} trades · {base['win_rate_pct']:.1f}% headline wins · {base['economic_win_rate_pct']:.1f}% economic winners · ${base['average_loss']:.2f} average loss · {base['maximum_drawdown_pct']:.2f}% drawdown**

## Fixed choices

| Entry-hours rule | Profit | Change | Trades | Headline wins | Economic wins | Avg loss | Drawdown | WF change | WF improved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

## Entry-time attribution with all hours enabled

| Entry UTC bucket | Trades | Profit | Win rate | Average P&L | Average loss |
|---|---:|---:|---:|---:|---:|
{hour_rows}

These outcomes are grouped by the hour the trade began. A later loss remains attributed to its original entry bucket.

## Six-month training selection

| Test window | Choice selected on prior 6 months | Training profit | Test profit | Current-block test | Change |
|---|---|---:|---:|---:|---:|
{selection_rows}

The causal selector chose {json.dumps(chosen_counts, sort_keys=True)}. Its combined test profit was **${selection_profit:.2f}**, versus **${control_profit:.2f}** for always blocking 06–12 UTC, a change of **${selection_profit - control_profit:+.2f}**.

## Decision

**Keep the current 06–12 UTC block unless both the fixed comparisons and the causal selector support a replacement.** A block that wins only on full-history hindsight is historical noise, not a deployment candidate. The August–September 2026 period remains post-selection data and is excluded from acceptance.
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
