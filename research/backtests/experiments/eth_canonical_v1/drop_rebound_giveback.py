"""Test wider givebacks on the accepted +0.30% net-floor ETH drop add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_min_net_floor import floor_candidates
from .drop_rebound_mode_b import drop_entries
from .drop_rebound_uptrend import _evaluate
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_giveback_v1.json"
CONTROL_GIVEBACK = 30.0


def wider_giveback_passes(row: dict, control: dict, base: dict,
                          acceptance: dict, safety: dict) -> bool:
    """A wider trail must improve the accepted strategy while retaining base safety."""
    return bool(
        row["giveback_pct"] != CONTROL_GIVEBACK
        and row["profit"] - control["profit"] > acceptance["full_profit_change_gt"]
        and row["later_profit"] - control["later_profit"] >= acceptance["later_profit_change_gte"]
        and row["walk_forward_profit"] - control["walk_forward_profit"]
        > acceptance["walk_forward_profit_change_gt"]
        and row["addon_average_win"] - control["addon_average_win"]
        > acceptance["addon_average_win_change_gt"]
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

    frozen = experiment["frozen_rule"]
    entries = drop_entries(market.close, int(frozen["lookback_minutes"]), float(frozen["fall_pct"]))
    results = {}
    for giveback in experiment["giveback_percentages"]:
        label = f"giveback_{float(giveback):.0f}pct"
        rule = {
            "activation_pct": frozen["activation_pct"],
            "giveback_pct": float(giveback),
            "protective_stop_pct": frozen["protective_stop_pct"],
        }
        addon = floor_candidates(
            entries, float(frozen["minimum_net_exit_pct"]), rule,
            portfolio.fee_per_side, portfolio.slippage_per_side,
        )
        results[label] = _evaluate(base_candidates + addon, market, windows, names, portfolio)

    rows = []
    for giveback in experiment["giveback_percentages"]:
        label = f"giveback_{float(giveback):.0f}pct"
        variant = results[label]
        metrics = _metrics(variant["full"])
        wf_changes_base = [
            variant[name].summary["net_profit"] - base_results[name].summary["net_profit"]
            for name in wf_names
        ]
        rows.append({
            "variant": label, "giveback_pct": float(giveback), **metrics,
            "profit_change_vs_base": metrics["profit"] - base["profit"],
            "additional_trades": metrics["trades"] - base["trades"],
            "later_profit": variant["later"].summary["net_profit"],
            "later_change_vs_base": (variant["later"].summary["net_profit"]
                                     - base_results["later"].summary["net_profit"]),
            "walk_forward_profit": sum(variant[name].summary["net_profit"] for name in wf_names),
            "walk_forward_change_vs_base": sum(wf_changes_base),
            "walk_forward_windows_improved_vs_base": sum(change > 0 for change in wf_changes_base),
            "post_selection_profit_change": (
                variant["post_selection_2026_08_09"].summary["net_profit"]
                - base_results["post_selection_2026_08_09"].summary["net_profit"]
            ),
        })
    variants = pd.DataFrame(rows)
    control = variants[variants.giveback_pct == CONTROL_GIVEBACK].iloc[0].to_dict()
    acceptance = experiment["acceptance_vs_current_best"]
    safety = experiment["base_safety"]
    final_rows = []
    for row in variants.to_dict("records"):
        row["profit_change_vs_control"] = row["profit"] - control["profit"]
        row["average_win_change_vs_control"] = row["average_win"] - control["average_win"]
        row["addon_average_win_change_vs_control"] = (
            row["addon_average_win"] - control["addon_average_win"]
        )
        row["win_rate_change_vs_control_pp"] = (
            row["headline_win_rate_pct"] - control["headline_win_rate_pct"]
        )
        row["later_change_vs_control"] = row["later_profit"] - control["later_profit"]
        row["walk_forward_change_vs_control"] = (
            row["walk_forward_profit"] - control["walk_forward_profit"]
        )
        row["accepted_replacement"] = wider_giveback_passes(
            row, control, base, acceptance, safety
        )
        final_rows.append(row)
    variants = pd.DataFrame(final_rows)
    accepted = variants[variants.accepted_replacement]
    if len(accepted):
        winner = accepted.sort_values("profit", ascending=False).iloc[0]
        decision = "replace_control"
    else:
        winner = variants[variants.giveback_pct == CONTROL_GIVEBACK].iloc[0]
        decision = "retain_30pct_control"

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
    headline = (f"REPLACE 30% WITH {winner.giveback_pct:.0f}%"
                if decision == "replace_control" else "KEEP 30% GIVEBACK")
    lines = [
        "# ETH drop-rebound giveback experiment", "", f"## Result: **{headline}**", "",
        "Every variant uses the accepted +0.30% minimum-net floor and is added behind the unchanged ETH base.", "",
        "| Giveback | Total profit | vs base | vs 30% | Overall WR | Add-on WR | Add-on avg win | Add-on avg loss | Later vs 30% | WF vs 30% | WF wins | Replace? |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants.itertuples(index=False):
        lines.append(
            f"| {row.giveback_pct:.0f}% | ${row.profit:.2f} | ${row.profit_change_vs_base:+.2f} | "
            f"${row.profit_change_vs_control:+.2f} | {row.headline_win_rate_pct:.1f}% | "
            f"{row.addon_win_rate_pct:.1f}% | ${row.addon_average_win:.2f} | "
            f"${row.addon_average_loss:.2f} | ${row.later_change_vs_control:+.2f} | "
            f"${row.walk_forward_change_vs_control:+.2f} | "
            f"{int(row.walk_forward_windows_improved_vs_base)}/6 | "
            f"{'yes' if row.accepted_replacement else 'control' if row.giveback_pct == CONTROL_GIVEBACK else 'no'} |"
        )
    lines.extend([
        "", "## Current ETH base", "",
        f"Profit **${base['profit']:.2f}**, {int(base['trades'])} trades, "
        f"{base['headline_win_rate_pct']:.1f}% win rate, average win **${base['average_win']:.2f}**.", "",
        "A wider giveback replaces 30% only if it improves full, later and walk-forward profit, "
        "raises add-on average win, keeps combined win rate within two percentage points, and "
        "continues to improve at least four of six windows versus the original base.", "",
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
    print(f"{summary['decision'].upper()}: giveback {summary['selected']['giveback_pct']:.0f}%")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
