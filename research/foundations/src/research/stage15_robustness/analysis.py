"""Dependence-aware robustness metrics for the frozen Step 5 strategy grid."""

import numpy as np
import pandas as pd


KEYS = ["asset", "timeframe", "average_type", "touch_zone", "policy", "condition_variant", "strategy"]
CONDITIONS = ["all_entries", "bullish_regime", "from_below", "rising_average"]
COSTS = [0.0, 0.1, 0.2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def condition_mask(frame, condition):
    if condition == "all_entries":
        return pd.Series(True, index=frame.index)
    if condition == "bullish_regime":
        return frame.origin_regime.eq("bullish")
    if condition == "from_below":
        return frame.approach.eq("from_below")
    if condition == "rising_average":
        return frame.average_slope_24h.eq("rising")
    raise ValueError(condition)


def select_nonoverlap(frame, duration_column):
    """Greedily retain the earliest signal when only one position is allowed."""
    ordered = frame[["entry_timestamp", "episode_id", duration_column]].sort_values(
        ["entry_timestamp", "episode_id"]
    )
    selected = []
    available = None
    for index, timestamp, duration_value in zip(
        ordered.index, ordered.entry_timestamp, ordered[duration_column]
    ):
        if available is None or timestamp >= available:
            selected.append(index)
            duration = float(duration_value)
            require(np.isfinite(duration) and duration >= 1, "Invalid exit duration")
            available = timestamp + pd.Timedelta(minutes=duration)
    return frame.loc[selected]


def quarter_labels(timestamps):
    return (
        timestamps.dt.year.astype(str)
        + "Q"
        + (((timestamps.dt.month - 1) // 3) + 1).astype(str)
    )


def expected_shortfall_10(values):
    if len(values) == 0:
        return np.nan
    return values.loc[values <= values.quantile(0.1)].mean()


def max_drawdown_pct(values):
    if len(values) == 0:
        return np.nan
    equity = np.cumprod(1 + values.to_numpy(float) / 100)
    peaks = np.maximum.accumulate(np.r_[1.0, equity])[:-1]
    drawdown = (equity / peaks - 1) * 100
    return float(drawdown.min())


def period_metrics(frame, return_column, duration_column):
    returns = frame[return_column]
    nonoverlap = select_nonoverlap(frame, duration_column)
    gross = nonoverlap[return_column]
    row = {
        "entries": len(frame),
        "mean_pct": returns.mean(),
        "median_pct": returns.median(),
        "positive_pct": returns.gt(0).mean() * 100 if len(frame) else np.nan,
        "nonoverlap_trades": len(nonoverlap),
        "overlap_removed_pct": (1 - len(nonoverlap) / len(frame)) * 100 if len(frame) else np.nan,
        "nonoverlap_gross_mean_pct": gross.mean(),
        "nonoverlap_gross_median_pct": gross.median(),
        "nonoverlap_expected_shortfall_10_pct": expected_shortfall_10(gross),
        "nonoverlap_max_drawdown_pct": max_drawdown_pct(gross),
        "median_duration_minutes": nonoverlap[duration_column].median(),
    }
    for cost in COSTS:
        net = gross - cost
        suffix = str(cost).replace(".", "_")
        row[f"nonoverlap_net_{suffix}_mean_pct"] = net.mean()
        row[f"nonoverlap_net_{suffix}_median_pct"] = net.median()
        row[f"nonoverlap_net_{suffix}_positive_pct"] = net.gt(0).mean() * 100 if len(net) else np.nan
    return row, nonoverlap


def block_mean_interval(frame, return_column, cost=0.2, repetitions=2000):
    if len(frame) < 30:
        return np.nan, np.nan, 0
    block = (
        (frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
        // pd.Timedelta(days=7)
    )
    values = frame[return_column] - cost
    stats = pd.DataFrame({"block": block, "value": values}).groupby("block").value.agg(["sum", "count"])
    if len(stats) < 8:
        return np.nan, np.nan, len(stats)
    rng = np.random.default_rng(1506)
    indices = rng.integers(0, len(stats), size=(repetitions, len(stats)))
    boot = stats["sum"].to_numpy()[indices].sum(axis=1) / stats["count"].to_numpy()[indices].sum(axis=1)
    low, high = np.quantile(boot, [0.025, 0.975])
    return low, high, len(stats)


def build_robustness(candidates, strategy_specs):
    eligible = candidates.loc[candidates.eligible & candidates.entered & candidates.exit_window_complete_24h].copy()
    rows, quarters = [], []
    config_keys = ["asset", "timeframe", "average_type", "touch_zone", "policy"]
    for key, setup in eligible.groupby(config_keys, observed=True, sort=True):
        for condition in CONDITIONS:
            chosen = setup.loc[condition_mask(setup, condition)]
            for strategy in strategy_specs:
                return_col = f"{strategy}_return_pct"
                duration_col = f"{strategy}_duration_minutes"
                strategy_frame = chosen[[
                    "episode_id", "entry_timestamp", "origin_signal_timestamp", "period",
                    return_col, duration_col,
                ]]
                row = {**dict(zip(config_keys, key)), "condition_variant": condition, "strategy": strategy}
                cached = {}
                for period in ["earlier", "later"]:
                    current = strategy_frame.loc[strategy_frame.period.eq(period)]
                    metrics, nonoverlap = period_metrics(current, return_col, duration_col)
                    row.update({f"{name}_{period}": value for name, value in metrics.items()})
                    cached[period] = nonoverlap
                    quarter_frame = nonoverlap.assign(
                        quarter=quarter_labels(nonoverlap.origin_signal_timestamp),
                        net_return=nonoverlap[return_col] - 0.2,
                    )
                    for quarter, group in quarter_frame.groupby("quarter", sort=True):
                        quarters.append({**dict(zip(config_keys, key)), "condition_variant": condition,
                                         "strategy": strategy, "period": period, "quarter": quarter,
                                         "trades": len(group), "net_0_2_mean_pct": group.net_return.mean(),
                                         "net_0_2_median_pct": group.net_return.median()})
                all_nonoverlap = pd.concat(cached.values()).sort_values("entry_timestamp")
                qmeans = (all_nonoverlap.assign(net=all_nonoverlap[return_col] - .2)
                          .groupby(quarter_labels(all_nonoverlap.origin_signal_timestamp)).net.mean())
                row["quarters"] = len(qmeans)
                row["positive_quarters_pct"] = qmeans.gt(0).mean() * 100 if len(qmeans) else np.nan
                row["worst_quarter_mean_pct"] = qmeans.min() if len(qmeans) else np.nan
                rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(quarters)


def attach_neighbors(frame):
    result = frame.copy()
    tf_order = ["1m", "3m", "5m"]
    zone_order = [0.5, 1.0, 1.5]
    lookup_keys = ["asset", "timeframe", "average_type", "touch_zone", "policy", "condition_variant", "strategy"]
    indexed = result.set_index(lookup_keys)
    counts, earlier_positive, later_positive = [], [], []
    for row in result.itertuples(index=False):
        neighbors = []
        ti, zi = tf_order.index(row.timeframe), zone_order.index(row.touch_zone)
        coordinates = []
        for index in [ti - 1, ti + 1]:
            if 0 <= index < len(tf_order): coordinates.append((tf_order[index], row.touch_zone))
        for index in [zi - 1, zi + 1]:
            if 0 <= index < len(zone_order): coordinates.append((row.timeframe, zone_order[index]))
        for timeframe, zone in coordinates:
            key = (row.asset, timeframe, row.average_type, zone, row.policy, row.condition_variant, row.strategy)
            if key in indexed.index:
                neighbors.append(indexed.loc[key])
        counts.append(len(neighbors))
        earlier_positive.append(sum(n["nonoverlap_net_0_2_mean_pct_earlier"] > 0 for n in neighbors))
        later_positive.append(sum(n["nonoverlap_net_0_2_mean_pct_later"] > 0 for n in neighbors))
    result["neighbor_count"] = counts
    result["positive_neighbors_earlier"] = earlier_positive
    result["positive_neighbors_later"] = later_positive
    result["neighbor_majority_positive_both"] = (
        result.neighbor_count.ge(2)
        & (result.positive_neighbors_earlier / result.neighbor_count).ge(.5)
        & (result.positive_neighbors_later / result.neighbor_count).ge(.5)
    )
    return result


def apply_selection(frame, candidates):
    result = attach_neighbors(frame)
    result["enough_samples"] = (
        result.entries_earlier.ge(100) & result.entries_later.ge(100)
        & result.nonoverlap_trades_earlier.ge(40) & result.nonoverlap_trades_later.ge(40)
    )
    result["positive_distribution_both"] = (
        result.mean_pct_earlier.gt(0) & result.mean_pct_later.gt(0)
        & result.median_pct_earlier.gt(0) & result.median_pct_later.gt(0)
    )
    result["cost_survives_both"] = (
        result.nonoverlap_net_0_2_mean_pct_earlier.gt(0)
        & result.nonoverlap_net_0_2_mean_pct_later.gt(0)
    )
    result["quarter_consistency"] = result.positive_quarters_pct.ge(60)
    result["tail_floor_both"] = (
        result.nonoverlap_expected_shortfall_10_pct_earlier.ge(-5)
        & result.nonoverlap_expected_shortfall_10_pct_later.ge(-5)
    )
    result["provisional_selection"] = (
        result.enough_samples & result.positive_distribution_both & result.cost_survives_both
        & result.quarter_consistency & result.tail_floor_both
        & result.neighbor_majority_positive_both
    )
    for period in ["earlier", "later"]:
        result[f"net_0_2_ci95_low_{period}"] = np.nan
        result[f"net_0_2_ci95_high_{period}"] = np.nan
        result[f"bootstrap_blocks_{period}"] = 0
    for index, row in result.loc[result.provisional_selection].iterrows():
        setup = candidates.loc[
            candidates.asset.eq(row.asset) & candidates.timeframe.eq(row.timeframe)
            & candidates.average_type.eq(row.average_type) & candidates.touch_zone.eq(row.touch_zone)
            & candidates.policy.eq(row.policy) & candidates.eligible & candidates.entered
            & candidates.exit_window_complete_24h
        ]
        setup = setup.loc[condition_mask(setup, row.condition_variant)]
        for period in ["earlier", "later"]:
            current = setup.loc[setup.period.eq(period)]
            nonoverlap = select_nonoverlap(current, f"{row.strategy}_duration_minutes")
            low, high, blocks = block_mean_interval(nonoverlap, f"{row.strategy}_return_pct")
            result.loc[index, f"net_0_2_ci95_low_{period}"] = low
            result.loc[index, f"net_0_2_ci95_high_{period}"] = high
            result.loc[index, f"bootstrap_blocks_{period}"] = blocks
    result["positive_block_ci_both"] = (
        result.net_0_2_ci95_low_earlier.gt(0) & result.net_0_2_ci95_low_later.gt(0)
    )
    result["robust_selection"] = result.provisional_selection & result.positive_block_ci_both
    result["worst_period_net_mean_pct"] = result[
        ["nonoverlap_net_0_2_mean_pct_earlier", "nonoverlap_net_0_2_mean_pct_later"]
    ].min(axis=1)
    return result.sort_values(
        ["robust_selection", "provisional_selection", "worst_period_net_mean_pct", "positive_quarters_pct"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
