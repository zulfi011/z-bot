"""Dependence-aware summaries and robustness checks for bounce entries."""

import numpy as np
import pandas as pd

from src.research.stage15_robustness.analysis import (
    block_mean_interval,
    expected_shortfall_10,
    max_drawdown_pct,
    quarter_labels,
    select_nonoverlap,
)


CONFIG_KEYS = ["asset", "timeframe", "average_type", "touch_zone", "policy"]


def summarize_period(frame):
    entered = frame.loc[frame.entered & frame.complete_24h].copy()
    selected = select_nonoverlap(entered, "duration_minutes") if len(entered) else entered
    gross = selected.gross_return_pct
    net = gross - .2
    counts = selected.exit_type.value_counts()
    return {
        "eligible_episodes": len(frame),
        "confirmed_entries": len(entered),
        "confirmation_rate_pct": len(entered) / len(frame) * 100 if len(frame) else np.nan,
        "nonoverlap_trades": len(selected),
        "overlap_removed_pct": (1 - len(selected) / len(entered)) * 100 if len(entered) else np.nan,
        "gross_mean_pct": gross.mean(),
        "gross_median_pct": gross.median(),
        "net_0_2_mean_pct": net.mean(),
        "net_0_2_median_pct": net.median(),
        "net_positive_pct": net.gt(0).mean() * 100 if len(net) else np.nan,
        "expected_shortfall_10_pct": expected_shortfall_10(gross),
        "max_drawdown_pct": max_drawdown_pct(net),
        "median_duration_minutes": selected.duration_minutes.median(),
        "target_count": int(counts.get("profit_target", 0)),
        "stop_count": int(counts.get("protective_stop", 0) + counts.get("ambiguous_stop", 0)),
        "time_count": int(counts.get("time", 0)),
        "target_pct": counts.get("profit_target", 0) / len(selected) * 100 if len(selected) else np.nan,
        "stop_pct": (counts.get("protective_stop", 0) + counts.get("ambiguous_stop", 0)) / len(selected) * 100 if len(selected) else np.nan,
        "time_pct": counts.get("time", 0) / len(selected) * 100 if len(selected) else np.nan,
    }, selected


def build_summary(candidates):
    eligible = candidates.loc[candidates.eligible].copy()
    rows, quarters = [], []
    for key, setup in eligible.groupby(CONFIG_KEYS, observed=True, sort=True):
        row = dict(zip(CONFIG_KEYS, key))
        chosen = {}
        for period in ["earlier", "later"]:
            metrics, selected = summarize_period(setup.loc[setup.period.eq(period)])
            row.update({f"{name}_{period}": value for name, value in metrics.items()})
            chosen[period] = selected
            if len(selected):
                qframe = selected.assign(
                    quarter=quarter_labels(selected.origin_signal_timestamp),
                    net_0_2_return_pct=selected.gross_return_pct - .2,
                )
                for quarter, group in qframe.groupby("quarter", sort=True):
                    quarters.append({**dict(zip(CONFIG_KEYS, key)), "period": period,
                                     "quarter": quarter, "trades": len(group),
                                     "net_0_2_mean_pct": group.net_0_2_return_pct.mean()})
        combined = pd.concat(chosen.values()).sort_values("entry_timestamp")
        qmeans = (combined.assign(net=combined.gross_return_pct - .2)
                  .groupby(quarter_labels(combined.origin_signal_timestamp)).net.mean())
        row["quarters"] = len(qmeans)
        row["positive_quarters_pct"] = qmeans.gt(0).mean() * 100 if len(qmeans) else np.nan
        row["worst_quarter_mean_pct"] = qmeans.min() if len(qmeans) else np.nan
        for period in ["earlier", "later"]:
            low, high, blocks = block_mean_interval(chosen[period], "gross_return_pct")
            row[f"net_ci95_low_{period}"] = low
            row[f"net_ci95_high_{period}"] = high
            row[f"bootstrap_blocks_{period}"] = blocks
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(quarters)


def attach_screen(summary):
    result = summary.copy()
    index = result.set_index(CONFIG_KEYS)
    tf_order = ["1m", "3m", "5m"]
    zone_order = [.5, 1., 1.5]
    counts, earlier, later = [], [], []
    for row in result.itertuples(index=False):
        neighbors = []
        ti, zi = tf_order.index(row.timeframe), zone_order.index(row.touch_zone)
        coordinates = []
        if ti > 0: coordinates.append((tf_order[ti - 1], row.touch_zone))
        if ti + 1 < len(tf_order): coordinates.append((tf_order[ti + 1], row.touch_zone))
        if zi > 0: coordinates.append((row.timeframe, zone_order[zi - 1]))
        if zi + 1 < len(zone_order): coordinates.append((row.timeframe, zone_order[zi + 1]))
        for timeframe, zone in coordinates:
            key = (row.asset, timeframe, row.average_type, zone, row.policy)
            if key in index.index:
                neighbors.append(index.loc[key])
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
        result.eligible_episodes_earlier.ge(100) & result.eligible_episodes_later.ge(100)
        & result.nonoverlap_trades_earlier.ge(40) & result.nonoverlap_trades_later.ge(40)
    )
    result["positive_distribution_both"] = (
        result.gross_mean_pct_earlier.gt(0) & result.gross_mean_pct_later.gt(0)
        & result.gross_median_pct_earlier.gt(0) & result.gross_median_pct_later.gt(0)
    )
    result["cost_survives_both"] = (
        result.net_0_2_mean_pct_earlier.gt(0) & result.net_0_2_mean_pct_later.gt(0)
    )
    result["quarter_consistency"] = result.positive_quarters_pct.ge(60)
    result["tail_floor_both"] = (
        result.expected_shortfall_10_pct_earlier.ge(-5)
        & result.expected_shortfall_10_pct_later.ge(-5)
    )
    result["provisional_pass"] = (
        result.enough_samples & result.positive_distribution_both & result.cost_survives_both
        & result.quarter_consistency & result.tail_floor_both
        & result.neighbor_majority_positive_both
    )
    result["positive_block_ci_both"] = (
        result.net_ci95_low_earlier.gt(0) & result.net_ci95_low_later.gt(0)
    )
    result["robust_pass"] = result.provisional_pass & result.positive_block_ci_both
    result["worst_period_net_mean_pct"] = result[
        ["net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later"]
    ].min(axis=1)
    return result.sort_values(
        ["robust_pass", "provisional_pass", "worst_period_net_mean_pct"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

