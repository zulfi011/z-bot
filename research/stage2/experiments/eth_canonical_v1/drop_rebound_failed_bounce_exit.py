"""Test causal time exits for unarmed trades in the best ETH drop-rebound add-on."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_min_net_floor import floor_candidates
from .drop_rebound_mode_b import drop_entries
from .drop_rebound_uptrend import _evaluate
from .engine import CandidateTrade, MarketData
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = (
    STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_failed_bounce_exit_v1.json"
)


def apply_failed_bounce_exit(candidates: list[CandidateTrade], checkpoint_minutes: int,
                             market: MarketData) -> tuple[list[CandidateTrade], int]:
    """Exit at next open if the checkpoint closes before a trade has armed."""
    adjusted = []
    changed = 0
    for candidate in candidates:
        checkpoint_close = candidate.entry + int(checkpoint_minutes) - 1
        exit_at = checkpoint_close + 1
        already_armed = (
            candidate.arm_index is not None and candidate.arm_index <= checkpoint_close
        )
        already_closed = candidate.exit <= checkpoint_close
        if already_armed or already_closed or exit_at >= len(market.open):
            adjusted.append(candidate)
            continue
        adjusted.append(replace(
            candidate, exit=exit_at, exit_price=float(market.open[exit_at]), exit_code=4,
            exit_kind="failed_bounce_time_exit", arm_index=None,
            candidate_id=f"{candidate.candidate_id}:failed-bounce-{checkpoint_minutes}m",
        ))
        changed += 1
    return adjusted, changed


def failed_bounce_passes(row: dict, control: dict, base: dict,
                         acceptance: dict, safety: dict) -> bool:
    return bool(
        row["profit"] - control["profit"] > acceptance["full_profit_change_gt"]
        and row["later_profit"] - control["later_profit"] >= acceptance["later_profit_change_gte"]
        and row["walk_forward_profit"] - control["walk_forward_profit"]
        > acceptance["walk_forward_profit_change_gt"]
        and row["addon_win_rate_pct"] - control["addon_win_rate_pct"]
        >= acceptance["addon_win_rate_change_gte_pp"]
        and row["addon_average_loss"] - control["addon_average_loss"]
        >= acceptance["addon_average_loss_change_gte"]
        and row["headline_win_rate_pct"]
        >= control["headline_win_rate_pct"] - acceptance["maximum_combined_win_rate_reduction_pp"]
        and row["headline_win_rate_pct"] >= safety["minimum_combined_headline_win_rate_pct"]
        and row["additional_trades"] >= safety["minimum_additional_trades"]
        and row["walk_forward_windows_improved_vs_base"]
        >= safety["minimum_walk_forward_windows_improved"]
        and row["average_loss"] >= base["average_loss"]
        and row["max_drawdown_pct"] >= base["max_drawdown_pct"]
    )


def run(config_path: Path = EXPERIMENT_CONFIG, output_dir: Path | None = None) -> Path:
    experiment = json.loads(config_path.read_text())
    baseline_config = json.loads(DEFAULT_CONFIG.read_text())
    portfolio = _portfolio_config(baseline_config)
    market, base_candidates, windows = baseline_module.build_baseline()
    names = baseline_config["evaluation"]["windows"]
    wf_names = [name for name in names if name.startswith("wf")]
    base_results = _evaluate(base_candidates, market, windows, names, portfolio)
    _assert_expected(base_results["full"].summary, baseline_config["acceptance"],
                     float(baseline_config["acceptance_tolerance"]))
    base = _metrics(base_results["full"])

    rule = experiment["frozen_rule"]
    entries = drop_entries(market.close, int(rule["lookback_minutes"]), float(rule["fall_pct"]))
    addon_control = floor_candidates(
        entries, float(rule["minimum_net_exit_pct"]), rule,
        portfolio.fee_per_side, portfolio.slippage_per_side,
    )
    addon_sets = {"no_time_exit_control": (addon_control, 0)}
    for checkpoint in experiment["failed_bounce_exit_minutes"]:
        adjusted, changed = apply_failed_bounce_exit(addon_control, int(checkpoint), market)
        addon_sets[f"exit_unarmed_{int(checkpoint)}m"] = (adjusted, changed)

    results = {
        label: _evaluate(base_candidates + addon, market, windows, names, portfolio)
        for label, (addon, _) in addon_sets.items()
    }
    rows = []
    for label, variant in results.items():
        metrics = _metrics(variant["full"])
        wf_changes = [
            variant[name].summary["net_profit"] - base_results[name].summary["net_profit"]
            for name in wf_names
        ]
        addon_trades = variant["full"].trades[variant["full"].trades.source == "drop_rebound"]
        rows.append({
            "variant": label, **metrics,
            "candidate_exits_changed": addon_sets[label][1],
            "filled_time_exits": int((addon_trades.exit_kind == "failed_bounce_time_exit").sum()),
            "profit_change_vs_base": metrics["profit"] - base["profit"],
            "additional_trades": metrics["trades"] - base["trades"],
            "later_profit": variant["later"].summary["net_profit"],
            "later_change_vs_base": (variant["later"].summary["net_profit"]
                                     - base_results["later"].summary["net_profit"]),
            "walk_forward_profit": sum(variant[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change_vs_base": sum(wf_changes),
            "walk_forward_windows_improved_vs_base": sum(change > 0 for change in wf_changes),
            "post_selection_profit_change": (
                variant["post_selection_2026_08_09"].summary["net_profit"]
                - base_results["post_selection_2026_08_09"].summary["net_profit"]
            ),
        })
    variants = pd.DataFrame(rows)
    control = variants[variants.variant == "no_time_exit_control"].iloc[0].to_dict()
    final_rows = []
    for row in variants.to_dict("records"):
        row["profit_change_vs_control"] = row["profit"] - control["profit"]
        row["later_change_vs_control"] = row["later_profit"] - control["later_profit"]
        row["walk_forward_change_vs_control"] = (
            row["walk_forward_profit"] - control["walk_forward_profit"]
        )
        row["accepted_replacement"] = bool(
            row["variant"] != "no_time_exit_control"
            and failed_bounce_passes(
                row, control, base, experiment["acceptance_vs_current_best"],
                experiment["base_safety"],
            )
        )
        final_rows.append(row)
    variants = pd.DataFrame(final_rows)
    accepted = variants[variants.accepted_replacement]
    if len(accepted):
        winner = accepted.sort_values("profit", ascending=False).iloc[0]
        decision = "replace_control"
    else:
        winner = variants[variants.variant == "no_time_exit_control"].iloc[0]
        decision = "retain_no_time_exit"

    window_rows = []
    for label, variant in results.items():
        for window in names:
            window_rows.append({
                "variant": label, "window": window,
                "profit": variant[window].summary["net_profit"],
                "base_profit": base_results[window].summary["net_profit"],
                "profit_change_vs_base": (variant[window].summary["net_profit"]
                                          - base_results[window].summary["net_profit"]),
                "trades": variant[window].summary["trades"],
                "win_rate_pct": variant[window].summary["win_rate_pct"],
            })

    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    variants.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    for label, variant in results.items():
        variant["full"].trades.to_csv(output / f"trades_{label}.csv", index=False)
    summary = {"decision": decision, "base": base, "selected": winner.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, winner, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, winner: pd.Series, decision: str) -> str:
    headline = (f"USE {winner.variant}" if decision == "replace_control" else "KEEP NO TIME EXIT")
    lines = [
        "# ETH drop-rebound failed-bounce time exit", "", f"## Result: **{headline}**", "",
        "Every variant uses the accepted 5%/60m entry, −2% stop, +0.19% arm, "
        "+0.30% minimum-net floor and 30% giveback.", "",
        "| Rule | Filled time exits | Extra trades | Profit | vs base | vs control | Overall WR | Add-on WR | Add-on avg loss | Later vs control | WF vs control | WF wins | Replace? |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants.itertuples(index=False):
        lines.append(
            f"| {row.variant} | {int(row.filled_time_exits)} | {int(row.additional_trades):+d} | "
            f"${row.profit:.2f} | ${row.profit_change_vs_base:+.2f} | "
            f"${row.profit_change_vs_control:+.2f} | {row.headline_win_rate_pct:.1f}% | "
            f"{row.addon_win_rate_pct:.1f}% | ${row.addon_average_loss:.2f} | "
            f"${row.later_change_vs_control:+.2f} | ${row.walk_forward_change_vs_control:+.2f} | "
            f"{int(row.walk_forward_windows_improved_vs_base)}/6 | "
            f"{'yes' if row.accepted_replacement else 'control' if row.variant == 'no_time_exit_control' else 'no'} |"
        )
    lines.extend([
        "", "## Current ETH base", "",
        f"Profit **${base['profit']:.2f}**, {int(base['trades'])} trades and "
        f"{base['headline_win_rate_pct']:.1f}% win rate.", "",
        "A time exit replaces the accepted control only if it improves full, later and walk-forward "
        "profit, does not reduce add-on win rate or worsen add-on average loss, and retains the "
        "original base-safety requirements.", "",
        "This is local ETH research only. No live bot or server files were changed.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = json.loads((output / "summary.json").read_text())
    print(f"{summary['decision'].upper()}: {summary['selected']['variant']}")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
