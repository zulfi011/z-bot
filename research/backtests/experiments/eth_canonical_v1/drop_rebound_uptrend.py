"""Test the rolling-drop ETH add-on only when all frozen uptrend checks pass."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline as baseline_module
from .drop_rebound_addon_quality import _metrics
from .drop_rebound_mode_b import drop_candidates, drop_entries
from .engine import ReplayResult, replay_portfolio
from .run import DEFAULT_CONFIG, STAGE2_ROOT, _assert_expected, _portfolio_config


EXPERIMENT_CONFIG = STAGE2_ROOT / "config" / "experiments" / "eth_drop_rebound_uptrend_v1.json"


def uptrend_passes(ema_now: float, ema_6h: float, close: float,
                    average_7d: float, average_15d: float, average_30d: float) -> bool:
    """The single preregistered uptrend predicate, evaluated at the drop trigger close."""
    values = np.asarray([ema_now, ema_6h, close, average_7d, average_15d, average_30d])
    if not np.isfinite(values).all():
        return False
    bearish_stack = average_7d < average_15d < average_30d
    return bool(ema_now > ema_6h and not bearish_stack and close > average_30d)


def filtered_drop_entries(immediate_entries: np.ndarray, raw: pd.DataFrame,
                          close: np.ndarray, ema_hours: int,
                          comparison_hours: int) -> tuple[np.ndarray, dict]:
    """Filter next-minute entries using information complete at their preceding trigger minute."""
    times = pd.DatetimeIndex(raw.open_time)
    if len(times) != len(close):
        raise ValueError("Raw candles and canonical close data are not aligned")
    ema = pd.Series(close).ewm(span=int(ema_hours) * 60, adjust=False).mean().to_numpy()
    lag = int(comparison_hours) * 60
    daily = {
        day: tuple(float(value) if value is not None else np.nan for value in values)
        for day, values in baseline_module.compare.replay.daily_averages(raw).items()
    }
    kept: list[int] = []
    funnel = {
        "drop_signals": int(len(immediate_entries)),
        "ema_rising": 0,
        "non_bearish_daily_stack": 0,
        "above_30d_average": 0,
        "all_uptrend_checks": 0,
    }
    for entry_value in immediate_entries:
        entry = int(entry_value)
        trigger = entry - 1
        if trigger < lag:
            continue
        average_7d, average_15d, average_30d = daily.get(
            times[trigger].floor("D"), (np.nan, np.nan, np.nan)
        )
        ema_rising = bool(ema[trigger] > ema[trigger - lag])
        non_bearish = bool(
            np.isfinite([average_7d, average_15d, average_30d]).all()
            and not (average_7d < average_15d < average_30d)
        )
        above_long = bool(np.isfinite(average_30d) and close[trigger] > average_30d)
        funnel["ema_rising"] += int(ema_rising)
        funnel["non_bearish_daily_stack"] += int(non_bearish)
        funnel["above_30d_average"] += int(above_long)
        if uptrend_passes(
            ema[trigger], ema[trigger - lag], close[trigger],
            average_7d, average_15d, average_30d,
        ):
            funnel["all_uptrend_checks"] += 1
            kept.append(entry)
    return np.asarray(kept, dtype=np.int64), funnel


def _evaluate(candidates, market, windows, names, portfolio) -> dict[str, ReplayResult]:
    return {name: replay_portfolio(candidates, market, *windows[name], portfolio) for name in names}


def _row(label: str, results: dict[str, ReplayResult], base_results: dict[str, ReplayResult],
         base: dict, wf_names: list[str], accepted_variant: bool, acceptance: dict) -> dict:
    full = _metrics(results["full"])
    changes = [
        results[name].summary["net_profit"] - base_results[name].summary["net_profit"]
        for name in wf_names
    ]
    row = {
        "variant": label, **full,
        "profit_change": full["profit"] - base["profit"],
        "additional_trades": full["trades"] - base["trades"],
        "later_profit_change": (results["later"].summary["net_profit"]
                                - base_results["later"].summary["net_profit"]),
        "walk_forward_profit_change": sum(changes),
        "walk_forward_windows_improved": sum(change > 0 for change in changes),
        "post_selection_profit_change": (
            results["post_selection_2026_08_09"].summary["net_profit"]
            - base_results["post_selection_2026_08_09"].summary["net_profit"]
        ),
    }
    row["accepted"] = bool(
        accepted_variant
        and row["headline_win_rate_pct"] >= acceptance["minimum_combined_headline_win_rate_pct"]
        and row["additional_trades"] >= acceptance["minimum_additional_trades"]
        and row["profit_change"] > acceptance["full_profit_change_gt"]
        and row["later_profit_change"] > acceptance["later_profit_change_gt"]
        and row["walk_forward_profit_change"] > acceptance["walk_forward_profit_change_gt"]
        and row["walk_forward_windows_improved"] >= acceptance["minimum_walk_forward_windows_improved"]
        and row["average_loss"] >= base["average_loss"]
        and row["max_drawdown_pct"] >= base["max_drawdown_pct"]
    )
    return row


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
    trend = experiment["uptrend_filter"]
    filtered, funnel = filtered_drop_entries(
        immediate, raw, market.close, int(trend["ema_hours"]),
        int(trend["ema_rising_comparison_hours"]),
    )
    cache: dict[tuple[int, float], tuple[int, float, int, int | None]] = {}
    candidate_sets = {}
    for label, entries in (("unfiltered_addon", immediate), ("uptrend_filtered_addon", filtered)):
        addon = drop_candidates(
            entries, market, int(rule["lookback_minutes"]), float(rule["fall_pct"]),
            float(rule["protective_stop_pct"]), float(rule["activation_pct"]),
            float(rule["giveback_pct"]), cache,
        )
        candidate_sets[label] = base_candidates + addon

    results = {
        label: _evaluate(candidates, market, windows, names, portfolio)
        for label, candidates in candidate_sets.items()
    }
    rows = [
        _row(label, variant_results, base_results, base, wf_names,
             label == "uptrend_filtered_addon", experiment["acceptance"])
        for label, variant_results in results.items()
    ]
    variants = pd.DataFrame(rows)
    filtered_row = variants[variants.variant == "uptrend_filtered_addon"].iloc[0]
    decision = "accept" if bool(filtered_row.accepted) else "reject"

    window_rows = []
    for label, variant_results in results.items():
        for name in names:
            window_rows.append({
                "variant": label, "window": name,
                "profit": variant_results[name].summary["net_profit"],
                "base_profit": base_results[name].summary["net_profit"],
                "profit_change": (variant_results[name].summary["net_profit"]
                                  - base_results[name].summary["net_profit"]),
                "trades": variant_results[name].summary["trades"],
                "win_rate_pct": variant_results[name].summary["win_rate_pct"],
            })

    output = output_dir or STAGE2_ROOT / "results" / experiment["experiment_id"]
    output.mkdir(parents=True, exist_ok=True)
    variants.to_csv(output / "variants.csv", index=False)
    pd.DataFrame(window_rows).to_csv(output / "window_results.csv", index=False)
    results["uptrend_filtered_addon"]["full"].trades.to_csv(output / "filtered_trades.csv", index=False)
    summary = {"decision": decision, "base": base, "signal_funnel": funnel,
               "filtered": filtered_row.to_dict()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    (output / "REPORT.md").write_text(_report(base, variants, funnel, decision))
    return output


def _report(base: dict, variants: pd.DataFrame, funnel: dict, decision: str) -> str:
    unfiltered = variants[variants.variant == "unfiltered_addon"].iloc[0]
    filtered = variants[variants.variant == "uptrend_filtered_addon"].iloc[0]
    return f"""# ETH drop-rebound uptrend-filter experiment

## Result: **{decision.upper()}**

The filter requires all three conditions at the completed drop candle: the 24-hour EMA is above
its value six hours earlier, the 7/15/30-day averages are not bearishly stacked, and price is
above the completed-day 30-day average.

| Metric | Current ETH base | Unfiltered add-on | Uptrend-filtered add-on |
|---|---:|---:|---:|
| Profit | ${base['profit']:.2f} | ${unfiltered.profit:.2f} | ${filtered.profit:.2f} |
| Profit change vs base | — | ${unfiltered.profit_change:+.2f} | ${filtered.profit_change:+.2f} |
| Trades | {int(base['trades'])} | {int(unfiltered.trades)} | {int(filtered.trades)} |
| Extra trades | — | {int(unfiltered.additional_trades):+d} | {int(filtered.additional_trades):+d} |
| Headline win rate | {base['headline_win_rate_pct']:.1f}% | {unfiltered.headline_win_rate_pct:.1f}% | {filtered.headline_win_rate_pct:.1f}% |
| Economic win rate | {base['economic_win_rate_pct']:.1f}% | {unfiltered.economic_win_rate_pct:.1f}% | {filtered.economic_win_rate_pct:.1f}% |
| Average loss | ${base['average_loss']:.2f} | ${unfiltered.average_loss:.2f} | ${filtered.average_loss:.2f} |
| Add-on trades / profit | — | {int(unfiltered.addon_trades)} / ${unfiltered.addon_profit:.2f} | {int(filtered.addon_trades)} / ${filtered.addon_profit:.2f} |
| Add-on win rate | — | {unfiltered.addon_win_rate_pct:.1f}% | {filtered.addon_win_rate_pct:.1f}% |
| Later-period change | — | ${unfiltered.later_profit_change:+.2f} | ${filtered.later_profit_change:+.2f} |
| Walk-forward change | — | ${unfiltered.walk_forward_profit_change:+.2f} | ${filtered.walk_forward_profit_change:+.2f} |
| Walk-forward windows improved | — | {int(unfiltered.walk_forward_windows_improved)}/6 | {int(filtered.walk_forward_windows_improved)}/6 |

## Signal funnel

- Original drop signals: {funnel['drop_signals']}
- EMA rising: {funnel['ema_rising']}
- Non-bearish daily stack: {funnel['non_bearish_daily_stack']}
- Above 30-day average: {funnel['above_30d_average']}
- Passed all three: {funnel['all_uptrend_checks']}

The filtered add-on is worth adding only if it remains above 75% combined win rate, adds at least
20 trades, improves full/later/walk-forward profit and at least four of six walk-forward windows,
without worsening average loss or drawdown.

This is local ETH research only. No live bot or server files were changed.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = run(args.config, args.output)
    summary = json.loads((output / "summary.json").read_text())
    print(f"{summary['decision'].upper()}: uptrend_filtered_addon")
    print(f"Artifacts: {output}")


if __name__ == "__main__":
    main()
