"""Portfolio-aware summaries for causal market filters."""

import numpy as np
import pandas as pd

from src.research.stage15_robustness.analysis import (
    block_mean_interval,
    expected_shortfall_10,
    max_drawdown_pct,
    quarter_labels,
    select_nonoverlap,
)
from .context import VARIANTS, filter_mask


CONFIG_KEYS = ["asset", "timeframe", "average_type", "touch_zone"]


def metrics(frame):
    selected = select_nonoverlap(frame, "duration_minutes") if len(frame) else frame
    gross = selected.gross_return_pct
    net = gross - .2
    exits = selected.exit_type.value_counts()
    return {
        "entries": len(frame),
        "nonoverlap_trades": len(selected),
        "overlap_removed_pct": (1 - len(selected) / len(frame)) * 100 if len(frame) else np.nan,
        "gross_mean_pct": gross.mean(),
        "gross_median_pct": gross.median(),
        "net_0_2_mean_pct": net.mean(),
        "net_0_2_median_pct": net.median(),
        "net_positive_pct": net.gt(0).mean() * 100 if len(net) else np.nan,
        "expected_shortfall_10_pct": expected_shortfall_10(gross),
        "max_drawdown_pct": max_drawdown_pct(net),
        "target_pct": exits.get("profit_target", 0) / len(selected) * 100 if len(selected) else np.nan,
        "stop_pct": (exits.get("protective_stop", 0) + exits.get("ambiguous_stop", 0)) / len(selected) * 100 if len(selected) else np.nan,
        "time_pct": exits.get("time", 0) / len(selected) * 100 if len(selected) else np.nan,
    }, selected


def build_analysis(candidates):
    base = candidates.loc[candidates.eligible & candidates.entered & candidates.complete_24h].copy()
    rows, quarters, complements = [], [], []
    for key, setup in base.groupby(CONFIG_KEYS, observed=True, sort=True):
        for variant in VARIANTS:
            mask = filter_mask(setup, variant)
            row = {**dict(zip(CONFIG_KEYS, key)), "filter_variant": variant}
            selected_periods = {}
            for period in ["earlier", "later"]:
                current = setup.loc[setup.period.eq(period)]
                accepted = current.loc[mask.loc[current.index]]
                rejected = current.loc[~mask.loc[current.index]]
                accepted_metrics, selected = metrics(accepted)
                rejected_metrics, _ = metrics(rejected)
                row.update({f"{name}_{period}": value for name, value in accepted_metrics.items()})
                row[f"retention_pct_{period}"] = len(accepted) / len(current) * 100 if len(current) else np.nan
                selected_periods[period] = selected
                complements.append({**dict(zip(CONFIG_KEYS, key)), "filter_variant": variant,
                                    "period": period, "accepted_entries": len(accepted),
                                    "rejected_entries": len(rejected),
                                    "accepted_net_mean_pct": accepted_metrics["net_0_2_mean_pct"],
                                    "rejected_net_mean_pct": rejected_metrics["net_0_2_mean_pct"],
                                    "accepted_minus_rejected_pp": accepted_metrics["net_0_2_mean_pct"] - rejected_metrics["net_0_2_mean_pct"]})
                if len(selected):
                    qframe = selected.assign(quarter=quarter_labels(selected.origin_signal_timestamp),
                                             net=selected.gross_return_pct - .2)
                    for quarter, group in qframe.groupby("quarter", sort=True):
                        quarters.append({**dict(zip(CONFIG_KEYS, key)), "filter_variant": variant,
                                         "period": period, "quarter": quarter, "trades": len(group),
                                         "net_0_2_mean_pct": group.net.mean()})
            combined = pd.concat(selected_periods.values()).sort_values("entry_timestamp")
            qmeans = (combined.assign(net=combined.gross_return_pct - .2)
                      .groupby(quarter_labels(combined.origin_signal_timestamp)).net.mean())
            row["quarters"] = len(qmeans)
            row["positive_quarters_pct"] = qmeans.gt(0).mean() * 100 if len(qmeans) else np.nan
            row["worst_quarter_mean_pct"] = qmeans.min() if len(qmeans) else np.nan
            for period in ["earlier", "later"]:
                low, high, blocks = block_mean_interval(selected_periods[period], "gross_return_pct")
                row[f"net_ci95_low_{period}"] = low
                row[f"net_ci95_high_{period}"] = high
                row[f"bootstrap_blocks_{period}"] = blocks
            rows.append(row)
    summary = pd.DataFrame(rows)
    baseline = summary.loc[summary.filter_variant.eq("all_market_conditions"),
                           [*CONFIG_KEYS, "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later"]]
    baseline = baseline.rename(columns={"net_0_2_mean_pct_earlier": "baseline_net_mean_earlier",
                                        "net_0_2_mean_pct_later": "baseline_net_mean_later"})
    summary = summary.merge(baseline, on=CONFIG_KEYS, validate="many_to_one")
    summary["net_improvement_earlier_pp"] = summary.net_0_2_mean_pct_earlier - summary.baseline_net_mean_earlier
    summary["net_improvement_later_pp"] = summary.net_0_2_mean_pct_later - summary.baseline_net_mean_later
    return summary, pd.DataFrame(quarters), pd.DataFrame(complements)


def screen(summary):
    result = summary.copy()
    index = result.set_index([*CONFIG_KEYS, "filter_variant"])
    tf_order = ["1m", "3m", "5m"]; zones = [.5, 1., 1.5]
    counts, earlier, later = [], [], []
    for row in result.itertuples(index=False):
        neighbors = []
        ti, zi = tf_order.index(row.timeframe), zones.index(row.touch_zone)
        coords = []
        if ti > 0: coords.append((tf_order[ti - 1], row.touch_zone))
        if ti + 1 < len(tf_order): coords.append((tf_order[ti + 1], row.touch_zone))
        if zi > 0: coords.append((row.timeframe, zones[zi - 1]))
        if zi + 1 < len(zones): coords.append((row.timeframe, zones[zi + 1]))
        for timeframe, zone in coords:
            key = (row.asset, timeframe, row.average_type, zone, row.filter_variant)
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
    result["improves_baseline_both"] = result.net_improvement_earlier_pp.gt(0) & result.net_improvement_later_pp.gt(0)
    result["provisional_pass"] = (
        result.enough_samples & result.positive_distribution_both & result.cost_survives_both
        & result.quarter_consistency & result.tail_floor_both
        & result.neighbor_majority_positive_both & result.improves_baseline_both
    )
    result["positive_block_ci_both"] = result.net_ci95_low_earlier.gt(0) & result.net_ci95_low_later.gt(0)
    result["robust_pass"] = result.provisional_pass & result.positive_block_ci_both
    result["worst_period_net_mean_pct"] = result[["net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later"]].min(axis=1)
    return result.sort_values(["robust_pass", "provisional_pass", "worst_period_net_mean_pct"],
                              ascending=[False, False, False]).reset_index(drop=True)

