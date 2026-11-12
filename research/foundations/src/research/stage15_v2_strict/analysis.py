"""Strict period, quarter, neighbor, tail, drawdown, and confidence checks."""

import numpy as np
import pandas as pd

from src.research.stage15_robustness.analysis import (
    expected_shortfall_10, max_drawdown_pct, quarter_labels, select_nonoverlap,
)


RETURN_COLUMN = "realistic_return_pct"
DURATION_COLUMN = "realistic_duration_minutes"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def filter_mask(frame, market_filter):
    if market_filter == "all_market_conditions":
        return pd.Series(True, index=frame.index)
    if market_filter == "avoid_strong_bearish":
        return ~frame.origin_regime.eq("bearish") & frame.origin_regime.ne("missing")
    if market_filter == "rising_15d":
        return frame.average_slope_24h.eq("rising")
    raise ValueError(market_filter)


def consecutive_losses(values):
    longest = current = 0
    for value in values:
        current = current + 1 if value <= 0 else 0
        longest = max(longest, current)
    return longest


def block_interval(frame, repetitions=5000, seed=1525):
    if len(frame) < 30:
        return np.nan, np.nan, 0
    blocks = ((frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
              // pd.Timedelta(days=7))
    stats = pd.DataFrame({"block": blocks, "value": frame[RETURN_COLUMN]}).groupby("block").value.agg(["sum", "count"])
    if len(stats) < 8:
        return np.nan, np.nan, len(stats)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(stats), size=(repetitions, len(stats)))
    sampled = stats["sum"].to_numpy()[indices].sum(axis=1) / stats["count"].to_numpy()[indices].sum(axis=1)
    low, high = np.quantile(sampled, [.025, .975])
    return low, high, len(stats)


def period_metrics(frame):
    selected = select_nonoverlap(frame, DURATION_COLUMN) if len(frame) else frame
    values = selected[RETURN_COLUMN]
    worst_five = values.nsmallest(min(5, len(values)))
    return {
        "entries": len(frame), "nonoverlap_trades": len(selected),
        "overlap_removed_pct": (1 - len(selected) / len(frame)) * 100 if len(frame) else np.nan,
        "mean_pct": values.mean(), "median_pct": values.median(),
        "positive_pct": values.gt(0).mean() * 100 if len(values) else np.nan,
        "worst_trade_pct": values.min(), "worst_5_mean_pct": worst_five.mean(),
        "expected_shortfall_10_pct": expected_shortfall_10(values),
        "max_drawdown_pct": max_drawdown_pct(values),
        "longest_nonpositive_streak": consecutive_losses(values),
    }, selected


def candidate_frame(candidates, definition):
    frame = candidates.loc[
        candidates.timeframe.eq(definition["timeframe"])
        & candidates.average_type.eq(definition["average_type"])
        & candidates.touch_zone.eq(definition["touch_zone"])
        & candidates.eligible & candidates.entered & candidates.execution_window_complete
    ]
    return frame.loc[filter_mask(frame, definition["market_filter"])]


def neighbor_rows(candidates, definition):
    tf_order = ["1m", "3m", "5m"]; zones = [.5, 1., 1.5]
    ti = tf_order.index(definition["timeframe"]); zi = zones.index(definition["touch_zone"])
    coordinates = []
    if ti > 0: coordinates.append((tf_order[ti - 1], definition["touch_zone"], "timeframe"))
    if ti + 1 < len(tf_order): coordinates.append((tf_order[ti + 1], definition["touch_zone"], "timeframe"))
    if zi > 0: coordinates.append((definition["timeframe"], zones[zi - 1], "touch_zone"))
    if zi + 1 < len(zones): coordinates.append((definition["timeframe"], zones[zi + 1], "touch_zone"))
    rows = []
    for timeframe, zone, changed in coordinates:
        neighbor = {**definition, "timeframe": timeframe, "touch_zone": zone}
        frame = candidate_frame(candidates, neighbor)
        row = {"candidate": definition["name"], "neighbor_timeframe": timeframe,
               "neighbor_touch_zone": zone, "changed_parameter": changed}
        for period in ["earlier", "later"]:
            metrics, _ = period_metrics(frame.loc[frame.period.eq(period)])
            row[f"trades_{period}"] = metrics["nonoverlap_trades"]
            row[f"mean_pct_{period}"] = metrics["mean_pct"]
        row["positive_both"] = row["mean_pct_earlier"] > 0 and row["mean_pct_later"] > 0
        rows.append(row)
    return rows


def analyze(candidates, definitions):
    summaries, quarters, neighbors, events = [], [], [], []
    for definition in definitions:
        frame = candidate_frame(candidates, definition)
        row = {"candidate": definition["name"], "timeframe": definition["timeframe"],
               "average_type": definition["average_type"], "touch_zone": definition["touch_zone"],
               "market_filter": definition["market_filter"]}
        selected_periods = []
        for period in ["earlier", "later"]:
            metrics, selected = period_metrics(frame.loc[frame.period.eq(period)])
            row.update({f"{name}_{period}": value for name, value in metrics.items()})
            low, high, blocks = block_interval(selected)
            row[f"ci95_low_{period}"] = low; row[f"ci95_high_{period}"] = high
            row[f"bootstrap_blocks_{period}"] = blocks
            selected_periods.append(selected)
            event = selected[["episode_id", "origin_signal_timestamp", "entry_timestamp",
                              RETURN_COLUMN, DURATION_COLUMN, "realistic_exit_type"]].copy()
            event["candidate"] = definition["name"]; event["period"] = period; events.append(event)
            if len(selected):
                qframe = selected.assign(quarter=quarter_labels(selected.origin_signal_timestamp))
                for quarter, group in qframe.groupby("quarter", sort=True):
                    quarters.append({"candidate": definition["name"], "period": period, "quarter": quarter,
                                     "trades": len(group), "mean_pct": group[RETURN_COLUMN].mean(),
                                     "median_pct": group[RETURN_COLUMN].median(),
                                     "positive_pct": group[RETURN_COLUMN].gt(0).mean() * 100})
        q = pd.DataFrame([item for item in quarters if item["candidate"] == definition["name"]])
        row["quarters"] = len(q); row["positive_quarters_pct"] = q.mean_pct.gt(0).mean() * 100
        row["worst_quarter_mean_pct"] = q.mean_pct.min()
        current_neighbors = neighbor_rows(candidates, definition); neighbors.extend(current_neighbors)
        row["neighbor_count"] = len(current_neighbors)
        row["positive_neighbors_both"] = sum(item["positive_both"] for item in current_neighbors)
        row["neighbor_majority_positive_both"] = (
            len(current_neighbors) >= 2 and row["positive_neighbors_both"] / len(current_neighbors) >= .5
        )
        row["enough_samples"] = (row["entries_earlier"] >= 100 and row["entries_later"] >= 100
                                  and row["nonoverlap_trades_earlier"] >= 40
                                  and row["nonoverlap_trades_later"] >= 40)
        row["positive_distribution_both"] = (row["mean_pct_earlier"] > 0 and row["mean_pct_later"] > 0
                                               and row["median_pct_earlier"] > 0 and row["median_pct_later"] > 0)
        row["quarter_consistency"] = row["positive_quarters_pct"] >= 60
        row["tail_floor_both"] = (row["expected_shortfall_10_pct_earlier"] >= -5
                                   and row["expected_shortfall_10_pct_later"] >= -5
                                   and row["worst_trade_pct_earlier"] >= -5
                                   and row["worst_trade_pct_later"] >= -5)
        row["drawdown_pass_both"] = (row["max_drawdown_pct_earlier"] >= -20
                                      and row["max_drawdown_pct_later"] >= -20)
        row["provisional_pass"] = (row["enough_samples"] and row["positive_distribution_both"]
                                    and row["quarter_consistency"] and row["tail_floor_both"]
                                    and row["drawdown_pass_both"] and row["neighbor_majority_positive_both"])
        row["positive_block_ci_both"] = row["ci95_low_earlier"] > 0 and row["ci95_low_later"] > 0
        row["strict_robust_pass"] = row["provisional_pass"] and row["positive_block_ci_both"]
        summaries.append(row)
    return (pd.DataFrame(summaries), pd.DataFrame(quarters), pd.DataFrame(neighbors),
            pd.concat(events, ignore_index=True))

