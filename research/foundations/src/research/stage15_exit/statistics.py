"""Summaries, paired comparisons, and robustness screens for Step 5 exits."""

import numpy as np
import pandas as pd

from .simulator import HOLD_MINUTES, TARGETS, TRAIL_GIVEBACKS, label


KEYS = ["asset", "timeframe", "average_type", "touch_zone", "policy"]


def strategy_specs():
    specs = []
    for minutes in HOLD_MINUTES:
        for risk in ["no_stop", "stop_4"]:
            specs.append((f"time_{minutes}_{risk}", "fixed_time", minutes, np.nan, np.nan, risk))
    for target in TARGETS:
        for risk in ["no_stop", "stop_4"]:
            specs.append((f"target_{label(target)}_{risk}", "profit_target", 1440, target, np.nan, risk))
    for giveback in TRAIL_GIVEBACKS:
        for risk in ["no_stop", "stop_4"]:
            specs.append((f"trail_{giveback}_{risk}", "trailing", 1440, 2.5, giveback, risk))
    return specs


def expected_shortfall_10(values):
    cutoff = values.quantile(0.1)
    return values.loc[values <= cutoff].mean()


def summarize(group, spec):
    name, family, hold_minutes, target, giveback, risk = spec
    returns = group[f"{name}_return_pct"]
    duration = group[f"{name}_duration_minutes"]
    type_column = f"{name}_exit_type"
    if type_column in group:
        exit_type = group[type_column]
    else:
        exit_type = pd.Series("time", index=group.index)
        if risk == "stop_4":
            exit_type = np.where(duration < hold_minutes, "protective_stop", "time")
            exit_type = pd.Series(exit_type, index=group.index)
    baseline = group.hold_1440m_return_pct
    delta = returns - baseline
    base_es = expected_shortfall_10(baseline)
    es = expected_shortfall_10(returns)
    return {
        "entries": len(group),
        "return_mean_pct": returns.mean(),
        "return_median_pct": returns.median(),
        "positive_return_pct": returns.gt(0).mean() * 100,
        "return_p10_pct": returns.quantile(0.1),
        "expected_shortfall_10_pct": es,
        "worst_return_pct": returns.min(),
        "baseline_hold_mean_pct": baseline.mean(),
        "baseline_hold_median_pct": baseline.median(),
        "baseline_expected_shortfall_10_pct": base_es,
        "mean_change_vs_hold_pp": delta.mean(),
        "median_change_vs_hold_pp": delta.median(),
        "tail_change_vs_hold_pp": es - base_es,
        "median_duration_minutes": duration.median(),
        "profit_target_exit_pct": exit_type.eq("profit_target").mean() * 100,
        "trailing_stop_exit_pct": exit_type.eq("trailing_stop").mean() * 100,
        "protective_stop_exit_pct": exit_type.isin(["protective_stop", "ambiguous_stop"]).mean() * 100,
        "ambiguous_exit_pct": exit_type.eq("ambiguous_stop").mean() * 100,
        "time_exit_pct": exit_type.eq("time").mean() * 100,
    }


def build_summaries(candidates):
    eligible = candidates.loc[
        candidates.eligible & candidates.entered & candidates.exit_window_complete_24h
    ].copy()
    masks = {
        "all_entries": pd.Series(True, index=eligible.index),
        "bullish_regime": eligible.origin_regime.eq("bullish"),
    }
    rows = []
    for segment, mask in masks.items():
        selected = eligible.loc[mask]
        for period in ["all", "earlier", "later"]:
            current = selected if period == "all" else selected.loc[selected.period.eq(period)]
            for key, group in current.groupby(KEYS, observed=True, sort=True):
                for spec in strategy_specs():
                    name, family, hold_minutes, target, giveback, risk = spec
                    rows.append({
                        **dict(zip(KEYS, key)), "segment": segment, "period": period,
                        "strategy": name, "exit_family": family, "risk_variant": risk,
                        "maximum_hold_minutes": hold_minutes, "target_pct": target,
                        "trail_giveback_pct": giveback, **summarize(group, spec),
                    })
    return pd.DataFrame(rows)


def block_interval(frame, strategy):
    delta = frame[f"{strategy}_return_pct"] - frame.hold_1440m_return_pct
    block = (
        (frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
        // pd.Timedelta(days=7)
    )
    stats = pd.DataFrame({"block": block, "delta": delta}).groupby("block").delta.agg(["sum", "count"])
    if len(frame) < 30 or len(stats) < 8:
        return np.nan, np.nan, len(stats)
    rng = np.random.default_rng(1505)
    indices = rng.integers(0, len(stats), size=(1000, len(stats)))
    boot = stats["sum"].to_numpy()[indices].sum(axis=1) / stats["count"].to_numpy()[indices].sum(axis=1)
    low, high = np.quantile(boot, [0.025, 0.975])
    return low, high, len(stats)


def build_stability_screen(summary, candidates):
    baseline_name = "time_1440_no_stop"
    alternatives = summary.loc[summary.strategy.ne(baseline_name)]
    join = [*KEYS, "segment", "strategy", "exit_family", "risk_variant",
            "maximum_hold_minutes", "target_pct", "trail_giveback_pct"]
    # NaN strategy parameters do not join reliably, so use sentinel copies.
    work = alternatives.copy()
    work["target_pct"] = work.target_pct.fillna(-1)
    work["trail_giveback_pct"] = work.trail_giveback_pct.fillna(-1)
    earlier = work.loc[work.period.eq("earlier")].drop(columns="period")
    later = work.loc[work.period.eq("later")].drop(columns="period")
    screen = earlier.merge(later, on=join, suffixes=("_earlier", "_later"), validate="one_to_one")
    screen["enough_entries"] = screen.entries_earlier.ge(100) & screen.entries_later.ge(100)
    screen["positive_mean_both"] = screen.return_mean_pct_earlier.gt(0) & screen.return_mean_pct_later.gt(0)
    screen["positive_median_both"] = screen.return_median_pct_earlier.gt(0) & screen.return_median_pct_later.gt(0)
    screen["mean_improved_both"] = screen.mean_change_vs_hold_pp_earlier.gt(0) & screen.mean_change_vs_hold_pp_later.gt(0)
    screen["tail_improved_both"] = screen.tail_change_vs_hold_pp_earlier.gt(0) & screen.tail_change_vs_hold_pp_later.gt(0)
    screen["stability_screen"] = (
        screen.enough_entries & screen.positive_mean_both & screen.positive_median_both
        & screen.mean_improved_both & screen.tail_improved_both
    )
    for period in ["earlier", "later"]:
        screen[f"mean_change_ci95_low_pp_{period}"] = np.nan
        screen[f"mean_change_ci95_high_pp_{period}"] = np.nan
        screen[f"week_blocks_{period}"] = 0
    eligible = candidates.loc[candidates.eligible & candidates.entered & candidates.exit_window_complete_24h]
    for index, row in screen.loc[screen.stability_screen].iterrows():
        setup = eligible.loc[
            eligible.asset.eq(row.asset) & eligible.timeframe.eq(row.timeframe)
            & eligible.average_type.eq(row.average_type) & eligible.touch_zone.eq(row.touch_zone)
            & eligible.policy.eq(row.policy)
        ]
        if row.segment == "bullish_regime":
            setup = setup.loc[setup.origin_regime.eq("bullish")]
        for period in ["earlier", "later"]:
            low, high, blocks = block_interval(setup.loc[setup.period.eq(period)], row.strategy)
            screen.loc[index, f"mean_change_ci95_low_pp_{period}"] = low
            screen.loc[index, f"mean_change_ci95_high_pp_{period}"] = high
            screen.loc[index, f"week_blocks_{period}"] = blocks
    screen["positive_block_ci_both"] = (
        screen.mean_change_ci95_low_pp_earlier.gt(0) & screen.mean_change_ci95_low_pp_later.gt(0)
    )
    screen.loc[screen.target_pct.eq(-1), "target_pct"] = np.nan
    screen.loc[screen.trail_giveback_pct.eq(-1), "trail_giveback_pct"] = np.nan
    return screen.sort_values(["stability_screen", "mean_change_vs_hold_pp_later"], ascending=[False, False]).reset_index(drop=True)


def build_cross_grid(summary):
    rows = []
    for key, group in summary.groupby(
        ["policy", "segment", "period", "strategy", "exit_family", "risk_variant"],
        observed=True, sort=True,
    ):
        rows.append({
            "policy": key[0], "segment": key[1], "period": key[2], "strategy": key[3],
            "exit_family": key[4], "risk_variant": key[5], "configurations": len(group),
            "median_return_mean_pct": group.return_mean_pct.median(),
            "configs_positive_mean": int(group.return_mean_pct.gt(0).sum()),
            "configs_mean_improved": int(group.mean_change_vs_hold_pp.gt(0).sum()),
            "configs_tail_improved": int(group.tail_change_vs_hold_pp.gt(0).sum()),
            "median_mean_change_vs_hold_pp": group.mean_change_vs_hold_pp.median(),
            "median_tail_change_vs_hold_pp": group.tail_change_vs_hold_pp.median(),
            "median_duration_minutes": group.median_duration_minutes.median(),
        })
    return pd.DataFrame(rows)
