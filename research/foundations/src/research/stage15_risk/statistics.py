"""Paired stop-versus-hold summaries and stability diagnostics."""

import numpy as np
import pandas as pd

from .simulator import STOP_LEVELS, stop_label


KEYS = ["asset", "timeframe", "average_type", "touch_zone", "policy"]


def expected_shortfall_10(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    cutoff = values.quantile(0.1)
    return values.loc[values <= cutoff].mean()


def summarize_policy(frame: pd.DataFrame, level: float | None) -> dict:
    hold = frame.audit_hold_return_24h_pct
    if level is None:
        returns = hold
        hit = pd.Series(False, index=frame.index)
        delta = returns - hold
        order = pd.Series("not_applicable", index=frame.index)
        times = pd.Series(np.nan, index=frame.index)
        fills = pd.Series(np.nan, index=frame.index)
    else:
        label = stop_label(level)
        returns = frame[f"stop_{label}_return_24h_pct"]
        hit = frame[f"stop_{label}_hit"].fillna(False).astype(bool)
        delta = frame[f"stop_{label}_paired_change_pp"]
        order = frame[f"stop_{label}_target_order"]
        times = frame[f"stop_{label}_time_minutes"]
        fills = frame[f"stop_{label}_fill_return_pct"]
    stopped = hit.sum()
    improved = hit & delta.gt(0)
    recovered = hit & hold.gt(0)
    later_target = order.eq("stop_first")
    ambiguous = order.eq("ambiguous_same_minute")
    return {
        "entries": len(frame),
        "stop_hit_count": int(stopped),
        "stop_hit_pct": hit.mean() * 100,
        "return_24h_mean_pct": returns.mean(),
        "return_24h_median_pct": returns.median(),
        "positive_24h_pct": returns.gt(0).mean() * 100,
        "return_24h_p10_pct": returns.quantile(0.1),
        "expected_shortfall_10_pct": expected_shortfall_10(returns),
        "worst_return_pct": returns.min(),
        "mean_change_vs_hold_pp": delta.mean(),
        "median_change_vs_hold_pp": delta.median(),
        "improved_episode_pct": improved.mean() * 100,
        "stopped_trade_improved_pct": improved.sum() / stopped * 100 if stopped else np.nan,
        "stopped_then_24h_positive_pct": recovered.sum() / stopped * 100 if stopped else np.nan,
        "stopped_before_later_target_pct": later_target.sum() / stopped * 100 if stopped else np.nan,
        "ambiguous_target_stop_pct": ambiguous.sum() / stopped * 100 if stopped else np.nan,
        "median_stop_time_minutes": times.loc[hit].median(),
        "worst_fill_return_pct": fills.loc[hit].min(),
    }


def build_summaries(candidates: pd.DataFrame) -> pd.DataFrame:
    eligible = candidates.loc[
        candidates.eligible & candidates.entered & candidates.stop_window_complete_24h
    ].copy()
    segments = {
        "all_entries": pd.Series(True, index=eligible.index),
        "bullish_regime": eligible.origin_regime.eq("bullish"),
    }
    rows = []
    for segment, mask in segments.items():
        selected = eligible.loc[mask]
        for period in ["all", "earlier", "later"]:
            current = selected if period == "all" else selected.loc[selected.period.eq(period)]
            for key, group in current.groupby(KEYS, observed=True, sort=True):
                for level in [None, *STOP_LEVELS]:
                    rows.append(
                        {
                            **dict(zip(KEYS, key)),
                            "segment": segment,
                            "period": period,
                            "protection": "no_stop" if level is None else f"stop_{level:g}",
                            "stop_pct": np.nan if level is None else level,
                            **summarize_policy(group, level),
                        }
                    )
    return pd.DataFrame(rows)


def _block_interval(frame: pd.DataFrame, level: float) -> tuple[float, float, int]:
    label = stop_label(level)
    block = (
        (frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
        // pd.Timedelta(days=7)
    )
    stats = pd.DataFrame(
        {"block": block, "delta": frame[f"stop_{label}_paired_change_pp"]}
    ).groupby("block").delta.agg(["sum", "count"])
    if len(frame) < 30 or len(stats) < 8:
        return np.nan, np.nan, len(stats)
    rng = np.random.default_rng(1504)
    indices = rng.integers(0, len(stats), size=(1000, len(stats)))
    boot = (
        stats["sum"].to_numpy()[indices].sum(axis=1)
        / stats["count"].to_numpy()[indices].sum(axis=1)
    )
    low, high = np.quantile(boot, [0.025, 0.975])
    return low, high, len(stats)


def build_stability_screen(summary: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    stops = summary.loc[summary.protection.ne("no_stop")]
    join = [*KEYS, "segment", "protection", "stop_pct"]
    earlier = stops.loc[stops.period.eq("earlier")].drop(columns="period")
    later = stops.loc[stops.period.eq("later")].drop(columns="period")
    screen = earlier.merge(later, on=join, suffixes=("_earlier", "_later"), validate="one_to_one")
    screen["enough_entries"] = screen.entries_earlier.ge(100) & screen.entries_later.ge(100)
    screen["mean_improved_both"] = (
        screen.mean_change_vs_hold_pp_earlier.gt(0)
        & screen.mean_change_vs_hold_pp_later.gt(0)
    )
    screen["p10_improved_both"] = (
        screen.return_24h_p10_pct_earlier.gt(-screen.stop_pct)
        & screen.return_24h_p10_pct_later.gt(-screen.stop_pct)
    )
    screen["tail_improved_both"] = (
        screen.expected_shortfall_10_pct_earlier.gt(-screen.stop_pct * 1.05)
        & screen.expected_shortfall_10_pct_later.gt(-screen.stop_pct * 1.05)
    )
    screen["positive_mean_both"] = (
        screen.return_24h_mean_pct_earlier.gt(0)
        & screen.return_24h_mean_pct_later.gt(0)
    )
    screen["stability_screen"] = (
        screen.enough_entries
        & screen.mean_improved_both
        & screen.tail_improved_both
        & screen.positive_mean_both
    )
    for period in ["earlier", "later"]:
        screen[f"mean_change_ci95_low_pp_{period}"] = np.nan
        screen[f"mean_change_ci95_high_pp_{period}"] = np.nan
        screen[f"week_blocks_{period}"] = 0
    eligible = candidates.loc[
        candidates.eligible & candidates.entered & candidates.stop_window_complete_24h
    ]
    for index, row in screen.loc[screen.stability_screen].iterrows():
        setup = eligible.loc[
            eligible.asset.eq(row.asset)
            & eligible.timeframe.eq(row.timeframe)
            & eligible.average_type.eq(row.average_type)
            & eligible.touch_zone.eq(row.touch_zone)
            & eligible.policy.eq(row.policy)
        ]
        if row.segment == "bullish_regime":
            setup = setup.loc[setup.origin_regime.eq("bullish")]
        for period in ["earlier", "later"]:
            current = setup.loc[setup.period.eq(period)]
            low, high, blocks = _block_interval(current, row.stop_pct)
            screen.loc[index, f"mean_change_ci95_low_pp_{period}"] = low
            screen.loc[index, f"mean_change_ci95_high_pp_{period}"] = high
            screen.loc[index, f"week_blocks_{period}"] = blocks
    screen["positive_block_ci_both"] = (
        screen.mean_change_ci95_low_pp_earlier.gt(0)
        & screen.mean_change_ci95_low_pp_later.gt(0)
    )
    return screen.sort_values(
        ["stability_screen", "mean_change_vs_hold_pp_later"], ascending=[False, False]
    ).reset_index(drop=True)


def build_cross_grid(summary: pd.DataFrame) -> pd.DataFrame:
    stops = summary.loc[summary.protection.ne("no_stop")]
    rows = []
    for key, group in stops.groupby(
        ["policy", "segment", "period", "protection", "stop_pct"],
        observed=True,
        sort=True,
    ):
        rows.append(
            {
                "policy": key[0],
                "segment": key[1],
                "period": key[2],
                "protection": key[3],
                "stop_pct": key[4],
                "configurations": len(group),
                "median_stop_hit_pct": group.stop_hit_pct.median(),
                "configs_mean_improved": int(group.mean_change_vs_hold_pp.gt(0).sum()),
                "median_mean_change_vs_hold_pp": group.mean_change_vs_hold_pp.median(),
                "median_stopped_then_positive_pct": group.stopped_then_24h_positive_pct.median(),
                "median_stopped_before_later_target_pct": group.stopped_before_later_target_pct.median(),
                "median_expected_shortfall_10_pct": group.expected_shortfall_10_pct.median(),
            }
        )
    return pd.DataFrame(rows)
