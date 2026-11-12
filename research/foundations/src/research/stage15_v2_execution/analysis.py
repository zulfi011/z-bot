"""Dependence-aware analysis of realistic spot execution scenarios."""

import numpy as np
import pandas as pd

from src.research.stage15_robustness.analysis import (
    expected_shortfall_10, max_drawdown_pct, quarter_labels, select_nonoverlap,
)
from .simulator import SCENARIOS


CONFIG_KEYS = ["asset", "timeframe", "average_type", "touch_zone", "market_filter", "scenario"]
MARKET_FILTERS = ["all_market_conditions", "avoid_strong_bearish"]


def market_mask(frame, market_filter):
    if market_filter == "all_market_conditions":
        return pd.Series(True, index=frame.index)
    if market_filter == "avoid_strong_bearish":
        return ~frame.origin_regime.eq("bearish") & frame.origin_regime.ne("missing")
    raise ValueError(market_filter)


def block_interval(frame, return_column, repetitions=2000):
    if len(frame) < 30:
        return np.nan, np.nan, 0
    block = ((frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
             // pd.Timedelta(days=7))
    stats = pd.DataFrame({"block": block, "value": frame[return_column]}).groupby("block").value.agg(["sum", "count"])
    if len(stats) < 8:
        return np.nan, np.nan, len(stats)
    rng = np.random.default_rng(1524)
    indices = rng.integers(0, len(stats), size=(repetitions, len(stats)))
    boot = stats["sum"].to_numpy()[indices].sum(axis=1) / stats["count"].to_numpy()[indices].sum(axis=1)
    low, high = np.quantile(boot, [.025, .975])
    return low, high, len(stats)


def metrics(frame, scenario):
    return_column = f"{scenario}_return_pct"; duration_column = f"{scenario}_duration_minutes"
    exit_column = f"{scenario}_exit_type"
    selected = select_nonoverlap(frame, duration_column) if len(frame) else frame
    values = selected[return_column]; exits = selected[exit_column].value_counts()
    return {
        "entries": len(frame), "nonoverlap_trades": len(selected),
        "overlap_removed_pct": (1 - len(selected) / len(frame)) * 100 if len(frame) else np.nan,
        "mean_return_pct": values.mean(), "median_return_pct": values.median(),
        "positive_pct": values.gt(0).mean() * 100 if len(values) else np.nan,
        "expected_shortfall_10_pct": expected_shortfall_10(values),
        "max_drawdown_pct": max_drawdown_pct(values),
        "target_pct": exits.get("profit_target", 0) / len(selected) * 100 if len(selected) else np.nan,
        "stop_pct": (exits.get("protective_stop", 0) + exits.get("ambiguous_stop", 0)) / len(selected) * 100 if len(selected) else np.nan,
        "time_pct": exits.get("time", 0) / len(selected) * 100 if len(selected) else np.nan,
        "median_duration_minutes": selected[duration_column].median(),
    }, selected


def build_analysis(candidates):
    base = candidates.loc[candidates.eligible & candidates.entered & candidates.execution_window_complete].copy()
    rows, quarters = [], []
    group_keys = ["asset", "timeframe", "average_type", "touch_zone"]
    for key, setup in base.groupby(group_keys, observed=True, sort=True):
        for market_filter in MARKET_FILTERS:
            filtered = setup.loc[market_mask(setup, market_filter)]
            for scenario in SCENARIOS:
                row = {**dict(zip(group_keys, key)), "market_filter": market_filter, "scenario": scenario}
                selected_periods = {}
                for period in ["earlier", "later"]:
                    result, selected = metrics(filtered.loc[filtered.period.eq(period)], scenario)
                    row.update({f"{name}_{period}": value for name, value in result.items()})
                    selected_periods[period] = selected
                    if len(selected):
                        column = f"{scenario}_return_pct"
                        qframe = selected.assign(quarter=quarter_labels(selected.origin_signal_timestamp))
                        for quarter, group in qframe.groupby("quarter", sort=True):
                            quarters.append({**dict(zip(group_keys, key)), "market_filter": market_filter,
                                             "scenario": scenario, "period": period, "quarter": quarter,
                                             "trades": len(group), "mean_return_pct": group[column].mean()})
                combined = pd.concat(selected_periods.values()).sort_values("entry_timestamp")
                column = f"{scenario}_return_pct"
                qmeans = combined.groupby(quarter_labels(combined.origin_signal_timestamp))[column].mean()
                row["quarters"] = len(qmeans)
                row["positive_quarters_pct"] = qmeans.gt(0).mean() * 100 if len(qmeans) else np.nan
                row["worst_quarter_mean_pct"] = qmeans.min() if len(qmeans) else np.nan
                for period in ["earlier", "later"]:
                    low, high, blocks = block_interval(selected_periods[period], column)
                    row[f"ci95_low_{period}"] = low; row[f"ci95_high_{period}"] = high
                    row[f"bootstrap_blocks_{period}"] = blocks
                rows.append(row)
    summary = pd.DataFrame(rows)
    gross = summary.loc[summary.scenario.eq("gross"),
                        ["asset", "timeframe", "average_type", "touch_zone", "market_filter",
                         "mean_return_pct_earlier", "mean_return_pct_later"]]
    gross = gross.rename(columns={"mean_return_pct_earlier": "gross_mean_earlier",
                                  "mean_return_pct_later": "gross_mean_later"})
    summary = summary.merge(gross, on=["asset", "timeframe", "average_type", "touch_zone", "market_filter"],
                            validate="many_to_one")
    summary["execution_drag_earlier_pp"] = summary.mean_return_pct_earlier - summary.gross_mean_earlier
    summary["execution_drag_later_pp"] = summary.mean_return_pct_later - summary.gross_mean_later
    return summary, pd.DataFrame(quarters)


def screen(summary):
    result = summary.copy(); index = result.set_index(CONFIG_KEYS)
    tf_order = ["1m", "3m", "5m"]; zones = [.5, 1., 1.5]
    counts, earlier, later = [], [], []
    for row in result.itertuples(index=False):
        neighbors = []; ti, zi = tf_order.index(row.timeframe), zones.index(row.touch_zone)
        coords = []
        if ti > 0: coords.append((tf_order[ti - 1], row.touch_zone))
        if ti + 1 < len(tf_order): coords.append((tf_order[ti + 1], row.touch_zone))
        if zi > 0: coords.append((row.timeframe, zones[zi - 1]))
        if zi + 1 < len(zones): coords.append((row.timeframe, zones[zi + 1]))
        for timeframe, zone in coords:
            key = (row.asset, timeframe, row.average_type, zone, row.market_filter, row.scenario)
            if key in index.index: neighbors.append(index.loc[key])
        counts.append(len(neighbors)); earlier.append(sum(n.mean_return_pct_earlier > 0 for n in neighbors))
        later.append(sum(n.mean_return_pct_later > 0 for n in neighbors))
    result["neighbor_count"] = counts; result["positive_neighbors_earlier"] = earlier
    result["positive_neighbors_later"] = later
    result["neighbor_majority_positive_both"] = (
        result.neighbor_count.ge(2) & (result.positive_neighbors_earlier / result.neighbor_count).ge(.5)
        & (result.positive_neighbors_later / result.neighbor_count).ge(.5))
    result["enough_samples"] = (result.entries_earlier.ge(100) & result.entries_later.ge(100)
                                 & result.nonoverlap_trades_earlier.ge(40)
                                 & result.nonoverlap_trades_later.ge(40))
    result["positive_distribution_both"] = (result.mean_return_pct_earlier.gt(0)
                                              & result.mean_return_pct_later.gt(0)
                                              & result.median_return_pct_earlier.gt(0)
                                              & result.median_return_pct_later.gt(0))
    result["quarter_consistency"] = result.positive_quarters_pct.ge(60)
    result["positive_block_ci_both"] = result.ci95_low_earlier.gt(0) & result.ci95_low_later.gt(0)
    result["execution_pass"] = (result.enough_samples & result.positive_distribution_both
                                 & result.quarter_consistency & result.neighbor_majority_positive_both)
    result["robust_pass"] = result.execution_pass & result.positive_block_ci_both
    result["worst_period_mean_pct"] = result[["mean_return_pct_earlier", "mean_return_pct_later"]].min(axis=1)
    return result.sort_values(["robust_pass", "execution_pass", "worst_period_mean_pct"],
                              ascending=[False, False, False]).reset_index(drop=True)

