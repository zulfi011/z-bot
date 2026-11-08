"""Test causal volatility-adjusted falls on the best ETH drop-rebound add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_higher_low import confirmation_passes_acceptance
from .drop_rebound_min_net_floor import floor_candidates
from .drop_rebound_mode_b import drop_entries
from .drop_rebound_uptrend import _evaluate
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_volatility_v1.json"


def completed_hourly_volatility(times: pd.DatetimeIndex, close: np.ndarray,
                                completed_returns: int) -> np.ndarray:
    """Map causal trailing hourly volatility to minutes using only completed hour buckets."""
    minute_close = pd.Series(np.asarray(close, dtype=float), index=times)
    hourly_close = minute_close.resample("1h", label="left", closed="left").last()
    hourly_log_return_pct = 100 * np.log(hourly_close / hourly_close.shift(1))
    volatility = hourly_log_return_pct.rolling(
        int(completed_returns), min_periods=int(completed_returns)
    ).std(ddof=1)
    volatility.index = volatility.index + pd.Timedelta(hours=1)
    return volatility.reindex(times.floor("h")).to_numpy(dtype=float)


def volatility_adjusted_entries(close: np.ndarray, hourly_volatility_pct: np.ndarray,
                                lookback_minutes: int, minimum_fall_pct: float,
                                volatility_multiple: float) -> np.ndarray:
    """Enter on the onset of the joint fixed-drop and volatility-normalized condition."""
    series = pd.Series(np.asarray(close, dtype=float))
    reference = series.shift(1).rolling(
        int(lookback_minutes), min_periods=int(lookback_minutes)
    ).max()
    drawdown_pct = 100 * (1 - series / reference)
    threshold = np.maximum(
        float(minimum_fall_pct), float(volatility_multiple) * hourly_volatility_pct
    )
    condition = np.isfinite(threshold) & (drawdown_pct.to_numpy() >= threshold)
    onset = condition & ~np.r_[False, condition[:-1]]
    signals = np.flatnonzero(onset)
    entries = signals + 1
    return entries[entries < len(series) - 1].astype(np.int64)


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
    volatility_config = experiment["volatility"]
    volatility = completed_hourly_volatility(
        market.times, market.close, int(volatility_config["completed_hourly_returns"])
    )
    fixed_entries = drop_entries(
        market.close, int(rule["lookback_minutes"]), float(rule["minimum_fall_pct"])
    )
    entries_by_label = {"fixed_5pct_control": fixed_entries}
    for multiple in volatility_config["multiples"]:
        label = f"fall_{float(multiple):.0f}x_hourly_vol"
        entries_by_label[label] = volatility_adjusted_entries(
            market.close, volatility, int(rule["lookback_minutes"]),
            float(rule["minimum_fall_pct"]), float(multiple),
        )

    results = {}
    for label, entries in entries_by_label.items():
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
            "variant": label, **metrics, "candidate_signals": len(entries_by_label[label]),
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
    control = variants[variants.variant == "fixed_5pct_control"].iloc[0].to_dict()
    final_rows = []
    for row in variants.to_dict("records"):
        row["profit_change_vs_control"] = row["profit"] - control["profit"]
        row["later_change_vs_control"] = row["later_profit"] - control["later_profit"]
        row["walk_forward_change_vs_control"] = (
            row["walk_forward_profit"] - control["walk_forward_profit"]
        )
        row["accepted_replacement"] = bool(
            row["variant"] != "fixed_5pct_control"
            and confirmation_passes_acceptance(
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
        winner = variants[variants.variant == "fixed_5pct_control"].iloc[0]
        decision = "retain_fixed_5pct"

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
    pd.DataFrame({"time": market.times, "hourly_volatility_pct": volatility}).to_csv(
        output / "hourly_volatility_by_minute.csv", index=False
    )
    for label, variant in results.items():
        variant["full"].trades.to_csv(output / f"trades_{label}.csv", index=False)
    summary = {"decision": decision, "base": base, "selected": winner.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, winner, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, winner: pd.Series, decision: str) -> str:
    headline = (f"USE {winner.variant}" if decision == "replace_control" else "KEEP FIXED 5% FALL")
    lines = [
        "# ETH drop-rebound volatility-adjusted fall experiment", "", f"## Result: **{headline}**", "",
        "Every variant uses the accepted −2% stop, +0.19% arm, +0.30% minimum-net floor and 30% giveback.", "",
        "| Entry | Signals | Extra trades | Profit | vs base | vs fixed | Overall WR | Add-on WR | Add-on avg loss | Later vs fixed | WF vs fixed | WF wins | Replace? |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants.itertuples(index=False):
        lines.append(
            f"| {row.variant} | {int(row.candidate_signals)} | {int(row.additional_trades):+d} | "
            f"${row.profit:.2f} | ${row.profit_change_vs_base:+.2f} | "
            f"${row.profit_change_vs_control:+.2f} | {row.headline_win_rate_pct:.1f}% | "
            f"{row.addon_win_rate_pct:.1f}% | ${row.addon_average_loss:.2f} | "
            f"${row.later_change_vs_control:+.2f} | ${row.walk_forward_change_vs_control:+.2f} | "
            f"{int(row.walk_forward_windows_improved_vs_base)}/6 | "
            f"{'yes' if row.accepted_replacement else 'control' if row.variant == 'fixed_5pct_control' else 'no'} |"
        )
    lines.extend([
        "", "## Current ETH base", "",
        f"Profit **${base['profit']:.2f}**, {int(base['trades'])} trades and "
        f"{base['headline_win_rate_pct']:.1f}% win rate.", "",
        "A volatility filter replaces the fixed fall only if it improves full, later and walk-forward "
        "profit versus the accepted control, does not reduce add-on win rate, keeps at least 20 extra "
        "trades and improves at least four of six windows versus the original base.", "",
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
