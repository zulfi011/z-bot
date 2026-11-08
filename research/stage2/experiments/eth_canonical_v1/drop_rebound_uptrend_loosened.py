"""Compare three preregistered loosened uptrend filters for the ETH drop add-on."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_mode_b import drop_candidates, drop_entries
from .drop_rebound_uptrend import _evaluate, _row
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = (
    STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_uptrend_loosened_v1.json"
)


def loosened_filter_passes(variant: dict, ema_now: float, ema_6h: float, close: float,
                           average_7d: float, average_15d: float,
                           average_30d: float) -> bool:
    """Evaluate only the causal checks enabled by a frozen variant."""
    if variant["require_ema_rising"] and not (
        np.isfinite(ema_now) and np.isfinite(ema_6h) and ema_now > ema_6h
    ):
        return False
    if variant["reject_bearish_daily_stack"]:
        averages = np.asarray([average_7d, average_15d, average_30d])
        if not np.isfinite(averages).all() or average_7d < average_15d < average_30d:
            return False
    if variant["require_above_30d"] and not (
        np.isfinite(close) and np.isfinite(average_30d) and close > average_30d
    ):
        return False
    return True


def entries_by_variant(immediate_entries: np.ndarray, raw: pd.DataFrame, close: np.ndarray,
                       variants: list[dict], ema_hours: int,
                       comparison_hours: int) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    times = pd.DatetimeIndex(raw.open_time)
    if len(times) != len(close):
        raise ValueError("Raw candles and canonical close data are not aligned")
    ema = pd.Series(close).ewm(span=int(ema_hours) * 60, adjust=False).mean().to_numpy()
    lag = int(comparison_hours) * 60
    daily = {
        day: tuple(float(value) if value is not None else np.nan for value in values)
        for day, values in baseline_module.compare.replay.daily_averages(raw).items()
    }
    selected = {variant["name"]: [] for variant in variants}
    feature_rows = []
    for entry_value in immediate_entries:
        entry = int(entry_value)
        trigger = entry - 1
        averages = daily.get(times[trigger].floor("D"), (np.nan, np.nan, np.nan))
        ema_6h = ema[trigger - lag] if trigger >= lag else np.nan
        feature = {
            "entry": entry, "trigger": trigger, "trigger_time": times[trigger],
            "ema_now": ema[trigger], "ema_6h": ema_6h, "trigger_close": close[trigger],
            "average_7d": averages[0], "average_15d": averages[1],
            "average_30d": averages[2],
        }
        for variant in variants:
            passed = loosened_filter_passes(
                variant, feature["ema_now"], feature["ema_6h"], feature["trigger_close"],
                feature["average_7d"], feature["average_15d"], feature["average_30d"],
            )
            feature[variant["name"]] = passed
            if passed:
                selected[variant["name"]].append(entry)
        feature_rows.append(feature)
    arrays = {name: np.asarray(entries, dtype=np.int64) for name, entries in selected.items()}
    return arrays, pd.DataFrame(feature_rows)


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

    rule = experiment["frozen_drop_rule"]
    immediate = drop_entries(market.close, int(rule["lookback_minutes"]), float(rule["fall_pct"]))
    raw, _ = baseline_module.compare.load("ETHUSDT")
    trend = experiment["trend_inputs"]
    filtered_entries, signal_features = entries_by_variant(
        immediate, raw, market.close, experiment["entry_variants"], int(trend["ema_hours"]),
        int(trend["ema_rising_comparison_hours"]),
    )

    cache: dict[tuple[int, float], tuple[int, float, int, int | None]] = {}
    candidate_sets = {}
    for variant in experiment["entry_variants"]:
        name = variant["name"]
        addon = drop_candidates(
            filtered_entries[name], market, int(rule["lookback_minutes"]), float(rule["fall_pct"]),
            float(rule["protective_stop_pct"]), float(rule["activation_pct"]),
            float(rule["giveback_pct"]), cache,
        )
        candidate_sets[name] = base_candidates + addon

    results = {
        name: _evaluate(candidates, market, windows, names, portfolio)
        for name, candidates in candidate_sets.items()
    }
    rows = []
    for name, variant_results in results.items():
        row = _row(
            name, variant_results, base_results, base, wf_names, True, experiment["acceptance"]
        )
        row["signals_passing_filter"] = int(signal_features[name].sum())
        rows.append(row)
    variants = pd.DataFrame(rows)
    accepted = variants[variants.accepted]
    decision = "accept" if len(accepted) else "reject"
    winner = (accepted.sort_values("profit", ascending=False).iloc[0] if len(accepted)
              else variants.sort_values("profit", ascending=False).iloc[0])

    window_rows = []
    for label, variant_results in results.items():
        for window in names:
            window_rows.append({
                "variant": label, "window": window,
                "profit": variant_results[window].summary["net_profit"],
                "base_profit": base_results[window].summary["net_profit"],
                "profit_change": (variant_results[window].summary["net_profit"]
                                  - base_results[window].summary["net_profit"]),
                "trades": variant_results[window].summary["trades"],
                "win_rate_pct": variant_results[window].summary["win_rate_pct"],
            })

    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    variants.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    signal_features.to_csv(output / "signal_features.csv", index=False)
    summary = {"decision": decision, "base": base, "best_variant": winner.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, decision: str) -> str:
    lines = [
        "# ETH drop-rebound loosened uptrend filters", "", f"## Result: **{decision.upper()}**", "",
        "All rows are additions behind the unchanged current ETH strategy.", "",
        "| Variant | Signals | Extra trades | Profit | Change | Overall WR | Add-on WR | Avg loss | Later | WF change | WF wins | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variants.itertuples(index=False):
        lines.append(
            f"| {row.variant} | {int(row.signals_passing_filter)} | {int(row.additional_trades):+d} | "
            f"${row.profit:.2f} | ${row.profit_change:+.2f} | {row.headline_win_rate_pct:.1f}% | "
            f"{row.addon_win_rate_pct:.1f}% | ${row.average_loss:.2f} | "
            f"${row.later_profit_change:+.2f} | ${row.walk_forward_profit_change:+.2f} | "
            f"{int(row.walk_forward_windows_improved)}/6 | {'yes' if row.accepted else 'no'} |"
        )
    lines.extend([
        "", "## Current base", "",
        f"Profit **${base['profit']:.2f}**, {int(base['trades'])} trades, "
        f"{base['headline_win_rate_pct']:.1f}% headline win rate and average loss "
        f"**${base['average_loss']:.2f}**.", "",
        "A variant passes only if it keeps overall win rate at 75%+, adds at least 20 trades, "
        "improves full/later/walk-forward profit and at least four of six walk-forward windows, "
        "without worsening average loss or drawdown.", "",
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
    print(f"{summary['decision'].upper()}: {summary['best_variant']['variant']}")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
