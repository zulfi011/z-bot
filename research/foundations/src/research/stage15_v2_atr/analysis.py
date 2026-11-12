"""Dependence-aware comparison of ATR and fixed spot exits."""

import numpy as np
import pandas as pd

from src.research.stage15_robustness.analysis import (
    block_mean_interval, expected_shortfall_10, max_drawdown_pct,
    quarter_labels, select_nonoverlap,
)
from .simulator import strategy_specs as atr_strategy_specs


CONFIG_KEYS = ["asset", "timeframe", "average_type", "touch_zone", "market_filter", "strategy"]
MARKET_FILTERS = ["all_market_conditions", "avoid_strong_bearish"]


def all_strategy_names():
    return ["fixed_target_4_stop_4"] + [item[0] for item in atr_strategy_specs()]


def market_mask(frame, market_filter):
    if market_filter == "all_market_conditions":
        return pd.Series(True, index=frame.index)
    if market_filter == "avoid_strong_bearish":
        return ~frame.origin_regime.eq("bearish") & frame.origin_regime.ne("missing")
    raise ValueError(market_filter)


def period_metrics(frame, strategy):
    return_column = f"{strategy}_return_pct"
    duration_column = f"{strategy}_duration_minutes"
    exit_column = f"{strategy}_exit_type"
    selected = select_nonoverlap(frame, duration_column) if len(frame) else frame
    gross = selected[return_column]; net = gross - .2
    exits = selected[exit_column].value_counts()
    stop_distance = selected[f"{strategy}_stop_distance_pct"]
    target_distance = selected[f"{strategy}_target_distance_pct"]
    return {
        "entries": len(frame), "nonoverlap_trades": len(selected),
        "overlap_removed_pct": (1 - len(selected) / len(frame)) * 100 if len(frame) else np.nan,
        "gross_mean_pct": gross.mean(), "gross_median_pct": gross.median(),
        "net_0_2_mean_pct": net.mean(), "net_0_2_median_pct": net.median(),
        "net_positive_pct": net.gt(0).mean() * 100 if len(net) else np.nan,
        "expected_shortfall_10_pct": expected_shortfall_10(gross),
        "max_drawdown_pct": max_drawdown_pct(net),
        "target_pct": exits.get("profit_target", 0) / len(selected) * 100 if len(selected) else np.nan,
        "stop_pct": (exits.get("protective_stop", 0) + exits.get("ambiguous_stop", 0)) / len(selected) * 100 if len(selected) else np.nan,
        "time_pct": exits.get("time", 0) / len(selected) * 100 if len(selected) else np.nan,
        "median_stop_distance_pct": stop_distance.median(),
        "median_target_distance_pct": target_distance.median(),
        "median_duration_minutes": selected[duration_column].median(),
    }, selected


def build_analysis(candidates):
    eligible = candidates.loc[candidates.eligible & candidates.entered & candidates.atr_window_complete].copy()
    rows, quarters = [], []
    group_keys = ["asset", "timeframe", "average_type", "touch_zone"]
    for key, setup in eligible.groupby(group_keys, observed=True, sort=True):
        for market_filter in MARKET_FILTERS:
            filtered = setup.loc[market_mask(setup, market_filter)]
            for strategy in all_strategy_names():
                row = {**dict(zip(group_keys, key)), "market_filter": market_filter, "strategy": strategy}
                selected_periods = {}
                for period in ["earlier", "later"]:
                    metrics, selected = period_metrics(filtered.loc[filtered.period.eq(period)], strategy)
                    row.update({f"{name}_{period}": value for name, value in metrics.items()})
                    selected_periods[period] = selected
                    if len(selected):
                        return_column = f"{strategy}_return_pct"
                        qframe = selected.assign(quarter=quarter_labels(selected.origin_signal_timestamp),
                                                 net=selected[return_column] - .2)
                        for quarter, group in qframe.groupby("quarter", sort=True):
                            quarters.append({**dict(zip(group_keys, key)), "market_filter": market_filter,
                                             "strategy": strategy, "period": period, "quarter": quarter,
                                             "trades": len(group), "net_0_2_mean_pct": group.net.mean()})
                combined = pd.concat(selected_periods.values()).sort_values("entry_timestamp")
                return_column = f"{strategy}_return_pct"
                qmeans = (combined.assign(net=combined[return_column] - .2)
                          .groupby(quarter_labels(combined.origin_signal_timestamp)).net.mean())
                row["quarters"] = len(qmeans)
                row["positive_quarters_pct"] = qmeans.gt(0).mean() * 100 if len(qmeans) else np.nan
                row["worst_quarter_mean_pct"] = qmeans.min() if len(qmeans) else np.nan
                for period in ["earlier", "later"]:
                    low, high, blocks = block_mean_interval(selected_periods[period], return_column)
                    row[f"net_ci95_low_{period}"] = low; row[f"net_ci95_high_{period}"] = high
                    row[f"bootstrap_blocks_{period}"] = blocks
                rows.append(row)
    summary = pd.DataFrame(rows)
    fixed = summary.loc[summary.strategy.eq("fixed_target_4_stop_4"),
                        ["asset", "timeframe", "average_type", "touch_zone", "market_filter",
                         "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later"]]
    fixed = fixed.rename(columns={"net_0_2_mean_pct_earlier": "fixed_net_mean_earlier",
                                  "net_0_2_mean_pct_later": "fixed_net_mean_later"})
    summary = summary.merge(fixed, on=["asset", "timeframe", "average_type", "touch_zone", "market_filter"],
                            validate="many_to_one")
    summary["improvement_over_fixed_earlier_pp"] = summary.net_0_2_mean_pct_earlier - summary.fixed_net_mean_earlier
    summary["improvement_over_fixed_later_pp"] = summary.net_0_2_mean_pct_later - summary.fixed_net_mean_later
    return summary, pd.DataFrame(quarters)


def screen(summary):
    result = summary.copy(); index = result.set_index(CONFIG_KEYS)
    tf_order = ["1m", "3m", "5m"]; zones = [.5, 1., 1.5]
    counts, earlier, later = [], [], []
    for row in result.itertuples(index=False):
        neighbors = []
        ti, zi = tf_order.index(row.timeframe), zones.index(row.touch_zone)
        coordinates = []
        if ti > 0: coordinates.append((tf_order[ti - 1], row.touch_zone))
        if ti + 1 < len(tf_order): coordinates.append((tf_order[ti + 1], row.touch_zone))
        if zi > 0: coordinates.append((row.timeframe, zones[zi - 1]))
        if zi + 1 < len(zones): coordinates.append((row.timeframe, zones[zi + 1]))
        for timeframe, zone in coordinates:
            key = (row.asset, timeframe, row.average_type, zone, row.market_filter, row.strategy)
            if key in index.index: neighbors.append(index.loc[key])
        counts.append(len(neighbors))
        earlier.append(sum(n.net_0_2_mean_pct_earlier > 0 for n in neighbors))
        later.append(sum(n.net_0_2_mean_pct_later > 0 for n in neighbors))
    result["neighbor_count"] = counts
    result["positive_neighbors_earlier"] = earlier
    result["positive_neighbors_later"] = later
    result["neighbor_majority_positive_both"] = (
        result.neighbor_count.ge(2)
        & (result.positive_neighbors_earlier / result.neighbor_count).ge(.5)
        & (result.positive_neighbors_later / result.neighbor_count).ge(.5)
    )
    result["enough_samples"] = (
        result.entries_earlier.ge(100) & result.entries_later.ge(100)
        & result.nonoverlap_trades_earlier.ge(40) & result.nonoverlap_trades_later.ge(40)
    )
    result["positive_distribution_both"] = (
        result.gross_mean_pct_earlier.gt(0) & result.gross_mean_pct_later.gt(0)
        & result.gross_median_pct_earlier.gt(0) & result.gross_median_pct_later.gt(0)
    )
    result["cost_survives_both"] = result.net_0_2_mean_pct_earlier.gt(0) & result.net_0_2_mean_pct_later.gt(0)
    result["quarter_consistency"] = result.positive_quarters_pct.ge(60)
    result["tail_floor_both"] = result.expected_shortfall_10_pct_earlier.ge(-5) & result.expected_shortfall_10_pct_later.ge(-5)
    result["improves_fixed_both"] = (
        result.improvement_over_fixed_earlier_pp.gt(0) & result.improvement_over_fixed_later_pp.gt(0)
    )
    result["provisional_pass"] = (
        result.strategy.ne("fixed_target_4_stop_4") & result.enough_samples
        & result.positive_distribution_both & result.cost_survives_both
        & result.quarter_consistency & result.tail_floor_both
        & result.neighbor_majority_positive_both & result.improves_fixed_both
    )
    result["positive_block_ci_both"] = result.net_ci95_low_earlier.gt(0) & result.net_ci95_low_later.gt(0)
    result["robust_pass"] = result.provisional_pass & result.positive_block_ci_both
    result["worst_period_net_mean_pct"] = result[["net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later"]].min(axis=1)
    return result.sort_values(["robust_pass", "provisional_pass", "worst_period_net_mean_pct"],
                              ascending=[False, False, False]).reset_index(drop=True)
