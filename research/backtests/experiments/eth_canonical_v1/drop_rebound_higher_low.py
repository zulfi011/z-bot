"""Test a causal higher-low reversal confirmation on the best ETH drop add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_min_net_floor import floor_candidates
from .drop_rebound_mode_b import drop_entries
from .drop_rebound_uptrend import _evaluate
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_higher_low_v1.json"


def _is_swing_low(low: np.ndarray, index: int, wing: int) -> bool:
    return bool(
        low[index] < np.min(low[index - wing:index])
        and low[index] <= np.min(low[index + 1:index + wing + 1])
    )


def higher_low_entries(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       immediate_entries: np.ndarray, wing: int,
                       maximum_minutes: int) -> tuple[np.ndarray, list[dict]]:
    """Find the next-open entry after a causally confirmed higher-low neckline break."""
    entries: list[int] = []
    episodes: list[dict] = []
    seen: set[int] = set()
    for immediate_value in immediate_entries:
        trigger = int(immediate_value) - 1
        last_breakout = min(trigger + maximum_minutes, len(close) - 2)
        first_swing = max(trigger, wing)
        last_swing = min(last_breakout - wing, len(low) - wing - 1)
        swings = [
            index for index in range(first_swing, last_swing + 1)
            if _is_swing_low(low, index, wing)
        ]
        selected = None
        for pair_index, (first, second) in enumerate(zip(swings, swings[1:])):
            if not low[second] > low[first]:
                continue
            between = high[first + 1:second]
            if not len(between):
                continue
            neckline = float(np.max(between))
            breakout_start = second + wing
            next_confirmation = (
                swings[pair_index + 2] + wing if pair_index + 2 < len(swings)
                else last_breakout + 1
            )
            breakout_end = min(last_breakout, next_confirmation - 1)
            if breakout_start > breakout_end:
                continue
            hits = np.flatnonzero(close[breakout_start:breakout_end + 1] > neckline)
            if not len(hits):
                continue
            breakout = breakout_start + int(hits[0])
            selected = {
                "trigger": trigger, "first_low": first, "second_low": second,
                "neckline": neckline, "breakout": breakout, "entry": breakout + 1,
            }
            break
        if selected is not None and selected["entry"] not in seen:
            seen.add(selected["entry"])
            entries.append(selected["entry"])
            episodes.append(selected)
    return np.asarray(entries, dtype=np.int64), episodes


def confirmation_passes_acceptance(row: dict, control: dict, base: dict,
                                   acceptance: dict, safety: dict) -> bool:
    return bool(
        row["profit"] - control["profit"] > acceptance["full_profit_change_gt"]
        and row["later_profit"] - control["later_profit"] >= acceptance["later_profit_change_gte"]
        and row["walk_forward_profit"] - control["walk_forward_profit"]
        > acceptance["walk_forward_profit_change_gt"]
        and row["addon_win_rate_pct"] - control["addon_win_rate_pct"]
        >= acceptance["addon_win_rate_change_gte_pp"]
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
    immediate = drop_entries(market.close, int(rule["lookback_minutes"]), float(rule["fall_pct"]))
    confirmation = experiment["confirmation"]
    confirmed, episodes = higher_low_entries(
        baseline_module.grid.HIGH, baseline_module.grid.LOW, market.close, immediate,
        int(confirmation["swing_wing_candles"]),
        int(confirmation["maximum_pattern_minutes_after_drop"]),
    )
    candidate_sets = {}
    for label, entries in (("immediate_control", immediate), ("higher_low_confirmation", confirmed)):
        addon = floor_candidates(
            entries, float(rule["minimum_net_exit_pct"]), rule,
            portfolio.fee_per_side, portfolio.slippage_per_side,
        )
        candidate_sets[label] = base_candidates + addon
    results = {
        label: _evaluate(candidates, market, windows, names, portfolio)
        for label, candidates in candidate_sets.items()
    }

    rows = []
    for label, variant in results.items():
        metrics = _metrics(variant["full"])
        wf_changes = [
            variant[name].summary["net_profit"] - base_results[name].summary["net_profit"]
            for name in wf_names
        ]
        rows.append({
            "variant": label, **metrics,
            "candidate_signals": len(immediate) if label == "immediate_control" else len(confirmed),
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
    control = variants[variants.variant == "immediate_control"].iloc[0].to_dict()
    final_rows = []
    for row in variants.to_dict("records"):
        row["profit_change_vs_control"] = row["profit"] - control["profit"]
        row["later_change_vs_control"] = row["later_profit"] - control["later_profit"]
        row["walk_forward_change_vs_control"] = (
            row["walk_forward_profit"] - control["walk_forward_profit"]
        )
        row["accepted_replacement"] = bool(
            row["variant"] == "higher_low_confirmation"
            and confirmation_passes_acceptance(
                row, control, base, experiment["acceptance_vs_current_best"],
                experiment["base_safety"],
            )
        )
        final_rows.append(row)
    variants = pd.DataFrame(final_rows)
    confirmed_row = variants[variants.variant == "higher_low_confirmation"].iloc[0]
    decision = "accept" if bool(confirmed_row.accepted_replacement) else "reject"

    episode_frame = pd.DataFrame(episodes)
    if len(episode_frame):
        for column in ("trigger", "first_low", "second_low", "breakout", "entry"):
            episode_frame[f"{column}_time"] = market.times[episode_frame[column].astype(int)]
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
    episode_frame.to_csv(output / "confirmed_episodes.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    for label, variant in results.items():
        variant["full"].trades.to_csv(output / f"trades_{label}.csv", index=False)
    summary = {"decision": decision, "base": base, "control": control,
               "confirmation": confirmed_row.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, decision: str) -> str:
    control = variants[variants.variant == "immediate_control"].iloc[0]
    confirmed = variants[variants.variant == "higher_low_confirmation"].iloc[0]
    return f"""# ETH drop-rebound higher-low confirmation

## Result: **{decision.upper()}**

Both versions use the accepted −2% stop, +0.19% arm, +0.30% minimum net floor and 30% giveback.

| Metric | Current ETH base | Immediate drop control | Higher-low confirmation |
|---|---:|---:|---:|
| Candidate signals | — | {int(control.candidate_signals)} | {int(confirmed.candidate_signals)} |
| Total trades | {int(base['trades'])} | {int(control.trades)} | {int(confirmed.trades)} |
| Extra trades | — | {int(control.additional_trades):+d} | {int(confirmed.additional_trades):+d} |
| Profit | ${base['profit']:.2f} | ${control.profit:.2f} | ${confirmed.profit:.2f} |
| Change vs base | — | ${control.profit_change_vs_base:+.2f} | ${confirmed.profit_change_vs_base:+.2f} |
| Change vs immediate | — | — | ${confirmed.profit_change_vs_control:+.2f} |
| Overall win rate | {base['headline_win_rate_pct']:.1f}% | {control.headline_win_rate_pct:.1f}% | {confirmed.headline_win_rate_pct:.1f}% |
| Add-on win rate | — | {control.addon_win_rate_pct:.1f}% | {confirmed.addon_win_rate_pct:.1f}% |
| Add-on average win | — | ${control.addon_average_win:.2f} | ${confirmed.addon_average_win:.2f} |
| Add-on average loss | — | ${control.addon_average_loss:.2f} | ${confirmed.addon_average_loss:.2f} |
| Later change vs immediate | — | — | ${confirmed.later_change_vs_control:+.2f} |
| Walk-forward change vs immediate | — | — | ${confirmed.walk_forward_change_vs_control:+.2f} |
| WF windows improved vs base | — | {int(control.walk_forward_windows_improved_vs_base)}/6 | {int(confirmed.walk_forward_windows_improved_vs_base)}/6 |

The higher-low rule replaces the immediate entry only if it improves full, later and walk-forward
profit versus the accepted control, does not reduce add-on win rate, keeps at least 20 additional
trades and still improves at least four of six windows versus the original ETH base.

This is local ETH research only. No live bot or server files were changed.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = json.loads((output / "summary.json").read_text())
    print(f"{summary['decision'].upper()}: higher_low_confirmation")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
