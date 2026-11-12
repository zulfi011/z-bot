"""Test one entry per causal fall episode on the best ETH drop-rebound add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_failed_bounce_exit import failed_bounce_passes
from .drop_rebound_min_net_floor import floor_candidates
from .drop_rebound_mode_b import drop_entries
from .drop_rebound_uptrend import _evaluate
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_episode_limit_v1.json"


def limit_entries_by_episode(close: np.ndarray, immediate_entries: np.ndarray,
                             lookback_minutes: int,
                             episode_minutes: int = 60) -> tuple[np.ndarray, pd.DataFrame]:
    """Keep one signal until recovery to its frozen high or the episode window expires."""
    accepted: list[int] = []
    records = []
    active_trigger: int | None = None
    active_high: float | None = None
    for entry_value in np.asarray(immediate_entries, dtype=np.int64):
        entry = int(entry_value)
        trigger = entry - 1
        original_high = float(np.max(close[max(0, trigger - lookback_minutes):trigger]))
        recovered = bool(
            active_trigger is not None and active_high is not None
            and np.any(close[active_trigger + 1:trigger + 1] >= active_high)
        )
        new_episode = bool(
            active_trigger is None or trigger >= active_trigger + int(episode_minutes)
        )
        allowed = active_trigger is None or recovered or new_episode
        records.append({
            "entry": entry, "trigger": trigger, "original_high": original_high,
            "allowed": allowed,
            "reason": ("first_episode" if active_trigger is None else
                       "recovered_original_high" if recovered else
                       "new_60m_episode" if new_episode else "duplicate_same_episode"),
        })
        if allowed:
            accepted.append(entry)
            active_trigger = trigger
            active_high = original_high
    return np.asarray(accepted, dtype=np.int64), pd.DataFrame(records)


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
    limited, episode_log = limit_entries_by_episode(
        market.close, immediate, int(rule["lookback_minutes"]), 60
    )
    entry_sets = {"unlimited_control": immediate, "one_per_fall_episode": limited}
    results = {}
    for label, entries in entry_sets.items():
        addon = floor_candidates(
            entries, float(rule["minimum_net_exit_pct"]), rule,
            portfolio.fee_per_side, portfolio.slippage_per_side,
        )
        results[label] = _evaluate(base_candidates + addon, market, windows, names, portfolio)

    rows = []
    for label, variant in results.items():
        metrics = _metrics(variant["full"])
        wf_changes = [
            variant[name].summary["net_profit"] - base_results[name].summary["net_profit"]
            for name in wf_names
        ]
        rows.append({
            "variant": label, **metrics, "candidate_signals": len(entry_sets[label]),
            "signals_removed": len(immediate) - len(entry_sets[label]),
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
    control = variants[variants.variant == "unlimited_control"].iloc[0].to_dict()
    final_rows = []
    for row in variants.to_dict("records"):
        row["profit_change_vs_control"] = row["profit"] - control["profit"]
        row["later_change_vs_control"] = row["later_profit"] - control["later_profit"]
        row["walk_forward_change_vs_control"] = (
            row["walk_forward_profit"] - control["walk_forward_profit"]
        )
        row["accepted_replacement"] = bool(
            row["variant"] == "one_per_fall_episode"
            and failed_bounce_passes(
                row, control, base, experiment["acceptance_vs_current_best"],
                experiment["base_safety"],
            )
        )
        final_rows.append(row)
    variants = pd.DataFrame(final_rows)
    limited_row = variants[variants.variant == "one_per_fall_episode"].iloc[0]
    decision = "accept" if bool(limited_row.accepted_replacement) else "reject"

    if len(episode_log):
        episode_log["trigger_time"] = market.times[episode_log.trigger.astype(int)]
        episode_log["entry_time"] = market.times[episode_log.entry.astype(int)]
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
    episode_log.to_csv(output / "episode_signal_log.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    for label, variant in results.items():
        variant["full"].trades.to_csv(output / f"trades_{label}.csv", index=False)
    summary = {"decision": decision, "base": base, "control": control,
               "episode_limited": limited_row.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, decision: str) -> str:
    control = variants[variants.variant == "unlimited_control"].iloc[0]
    limited = variants[variants.variant == "one_per_fall_episode"].iloc[0]
    return f"""# ETH drop-rebound episode-limit experiment

## Result: **{decision.upper()}**

Both versions use the accepted 5%/60m entry, −2% stop, +0.19% arm,
+0.30% minimum-net floor and 30% giveback.

| Metric | Current ETH base | Unlimited add-on | One per fall episode |
|---|---:|---:|---:|
| Candidate signals | — | {int(control.candidate_signals)} | {int(limited.candidate_signals)} |
| Signals removed | — | 0 | {int(limited.signals_removed)} |
| Extra filled trades | — | {int(control.additional_trades):+d} | {int(limited.additional_trades):+d} |
| Total profit | ${base['profit']:.2f} | ${control.profit:.2f} | ${limited.profit:.2f} |
| Change vs base | — | ${control.profit_change_vs_base:+.2f} | ${limited.profit_change_vs_base:+.2f} |
| Change vs unlimited | — | — | ${limited.profit_change_vs_control:+.2f} |
| Overall win rate | {base['headline_win_rate_pct']:.1f}% | {control.headline_win_rate_pct:.1f}% | {limited.headline_win_rate_pct:.1f}% |
| Add-on win rate | — | {control.addon_win_rate_pct:.1f}% | {limited.addon_win_rate_pct:.1f}% |
| Add-on average loss | — | ${control.addon_average_loss:.2f} | ${limited.addon_average_loss:.2f} |
| Later change vs unlimited | — | — | ${limited.later_change_vs_control:+.2f} |
| Walk-forward change vs unlimited | — | — | ${limited.walk_forward_change_vs_control:+.2f} |
| WF windows improved vs base | — | {int(control.walk_forward_windows_improved_vs_base)}/6 | {int(limited.walk_forward_windows_improved_vs_base)}/6 |

The episode limit replaces the accepted control only if it improves full, later and walk-forward
profit, does not reduce add-on win rate or worsen its average loss, and retains all base-safety rules.

This is local ETH research only. No live bot or server files were changed.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = json.loads((output / "summary.json").read_text())
    print(f"{summary['decision'].upper()}: one_per_fall_episode")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
