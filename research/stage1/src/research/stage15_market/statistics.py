"""Condition summaries, complement comparisons, and stability screens."""

import numpy as np
import pandas as pd


KEYS = ["asset", "timeframe", "average_type", "touch_zone", "rule", "wait_minutes", "policy"]
DIMENSIONS = ["origin_regime", "approach", "average_slope_24h", "prior_return_sign",
              "prior_range_band", "touch_close_side", "regime_approach"]
MISSING_VALUES = {"missing", "unknown", "missing__unknown"}


def metrics(frame: pd.DataFrame) -> dict:
    entered = frame.loc[frame.entered]
    n = len(entered)
    mae = entered.mae_1440m_pct.median()
    mfe = entered.mfe_1440m_pct.median()
    outcomes = entered["first_2.5"].value_counts()
    decisive = outcomes.get("target_first", 0) + outcomes.get("stop_first", 0)
    return {
        "eligible_episodes": len(frame),
        "entries": n,
        "entry_rate_pct": n / len(frame) * 100 if len(frame) else np.nan,
        "return_24h_mean_pct": entered.return_1440m_pct.mean(),
        "return_24h_median_pct": entered.return_1440m_pct.median(),
        "positive_24h_pct": entered.return_1440m_pct.gt(0).mean() * 100 if n else np.nan,
        "mae_24h_median_pct": mae,
        "mae_24h_p10_pct": entered.mae_1440m_pct.quantile(.1),
        "mfe_24h_median_pct": mfe,
        "mfe_mae_ratio": mfe / abs(mae) if pd.notna(mae) and mae != 0 else np.nan,
        "target_2_5_reach_pct": entered.target_2_5_reached.mean() * 100 if n else np.nan,
        "target_first_2_5_all_pct": outcomes.get("target_first", 0) / n * 100 if n else np.nan,
        "target_first_2_5_decisive_pct": outcomes.get("target_first", 0) / decisive * 100 if decisive else np.nan,
    }


def block_difference_interval(selected: pd.DataFrame, complement: pd.DataFrame):
    """Exploratory seven-day block CI for mean return difference."""
    selected = selected.loc[selected.entered]
    complement = complement.loc[complement.entered]
    if len(selected) < 30 or len(complement) < 30:
        return np.nan, np.nan, 0
    frames = []
    for name, frame in [("selected", selected), ("complement", complement)]:
        block = ((frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
                 // pd.Timedelta(days=7))
        part = pd.DataFrame({"block": block, "value": frame.return_1440m_pct})
        part = part.groupby("block").value.agg(["sum", "count"])
        part.columns = [f"{name}_sum", f"{name}_count"]
        frames.append(part)
    blocks = frames[0].join(frames[1], how="outer").fillna(0)
    if len(blocks) < 8:
        return np.nan, np.nan, len(blocks)
    rng = np.random.default_rng(1503)
    sampled = rng.integers(0, len(blocks), size=(1000, len(blocks)))
    values = blocks.to_numpy()[sampled]
    selected_sum = values[:, :, 0].sum(axis=1)
    selected_count = values[:, :, 1].sum(axis=1)
    complement_sum = values[:, :, 2].sum(axis=1)
    complement_count = values[:, :, 3].sum(axis=1)
    selected_mean = np.divide(
        selected_sum, selected_count, out=np.full_like(selected_sum, np.nan),
        where=selected_count > 0,
    )
    complement_mean = np.divide(
        complement_sum, complement_count, out=np.full_like(complement_sum, np.nan),
        where=complement_count > 0,
    )
    differences = selected_mean - complement_mean
    valid = np.isfinite(differences)
    if not valid.any():
        return np.nan, np.nan, len(blocks)
    low, high = np.quantile(differences[valid], [.025, .975])
    return low, high, len(blocks)


def build_condition_summaries(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    eligible = frame.loc[frame.eligible].copy()
    for column in [*KEYS, *DIMENSIONS, "period"]:
        eligible[column] = eligible[column].astype("object")
    for period in ["all", "earlier", "later"]:
        current = eligible if period == "all" else eligible.loc[eligible.period.eq(period)]
        for key, setup in current.groupby(KEYS, observed=True, sort=True):
            overall = metrics(setup)
            for dimension in DIMENSIONS:
                for value, selected in setup.groupby(dimension, observed=True, sort=True, dropna=False):
                    complement = setup.loc[~setup[dimension].eq(value)]
                    chosen = metrics(selected)
                    other = metrics(complement)
                    rows.append({
                        **dict(zip(KEYS, key)), "period": period,
                        "condition": dimension, "value": str(value),
                        **chosen,
                        "overall_entries": overall["entries"],
                        "overall_return_24h_mean_pct": overall["return_24h_mean_pct"],
                        "overall_return_24h_median_pct": overall["return_24h_median_pct"],
                        "complement_entries": other["entries"],
                        "complement_return_24h_mean_pct": other["return_24h_mean_pct"],
                        "complement_return_24h_median_pct": other["return_24h_median_pct"],
                        "mean_advantage_vs_complement_pp": (
                            chosen["return_24h_mean_pct"] - other["return_24h_mean_pct"]
                        ),
                        "median_advantage_vs_complement_pp": (
                            chosen["return_24h_median_pct"] - other["return_24h_median_pct"]
                        ),
                    })
    return pd.DataFrame(rows)


def build_stability_screen(summary: pd.DataFrame) -> pd.DataFrame:
    earlier = summary.loc[summary.period.eq("earlier")].drop(columns="period")
    later = summary.loc[summary.period.eq("later")].drop(columns="period")
    join = [*KEYS, "condition", "value"]
    result = earlier.merge(later, on=join, suffixes=("_earlier", "_later"), validate="one_to_one")
    result["nonmissing_condition"] = ~result.value.isin(MISSING_VALUES)
    result["enough_entries"] = result.entries_earlier.ge(100) & result.entries_later.ge(100)
    result["positive_mean_both"] = (
        result.return_24h_mean_pct_earlier.gt(0) & result.return_24h_mean_pct_later.gt(0)
    )
    result["positive_median_both"] = (
        result.return_24h_median_pct_earlier.gt(0) & result.return_24h_median_pct_later.gt(0)
    )
    result["mfe_mae_above_one_both"] = (
        result.mfe_mae_ratio_earlier.gt(1) & result.mfe_mae_ratio_later.gt(1)
    )
    result["mean_beats_complement_both"] = (
        result.mean_advantage_vs_complement_pp_earlier.gt(0)
        & result.mean_advantage_vs_complement_pp_later.gt(0)
    )
    result["stability_screen"] = (
        result.nonmissing_condition & result.enough_entries & result.positive_mean_both
        & result.positive_median_both & result.mfe_mae_above_one_both
        & result.mean_beats_complement_both
    )
    return result.sort_values(
        ["stability_screen", "mean_advantage_vs_complement_pp_later"],
        ascending=[False, False],
    ).reset_index(drop=True)


def attach_screen_intervals(screen: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """Bootstrap only hypotheses that pass the non-bootstrap stability screen."""
    result = screen.copy()
    for period in ["earlier", "later"]:
        result[f"mean_difference_ci95_low_pp_{period}"] = np.nan
        result[f"mean_difference_ci95_high_pp_{period}"] = np.nan
        result[f"week_blocks_{period}"] = 0
    for index, row in result.loc[result.stability_screen].iterrows():
        setup = candidates.loc[
            candidates.eligible & candidates.asset.eq(row.asset)
            & candidates.timeframe.eq(row.timeframe)
            & candidates.average_type.eq(row.average_type)
            & candidates.touch_zone.eq(row.touch_zone)
            & candidates.policy.eq(row.policy)
        ]
        for period in ["earlier", "later"]:
            current = setup.loc[setup.period.eq(period)]
            selected = current.loc[current[row.condition].astype(str).eq(str(row.value))]
            complement = current.loc[~current[row.condition].astype(str).eq(str(row.value))]
            low, high, blocks = block_difference_interval(selected, complement)
            result.loc[index, f"mean_difference_ci95_low_pp_{period}"] = low
            result.loc[index, f"mean_difference_ci95_high_pp_{period}"] = high
            result.loc[index, f"week_blocks_{period}"] = blocks
    result["positive_block_ci_both"] = (
        result.mean_difference_ci95_low_pp_earlier.gt(0)
        & result.mean_difference_ci95_low_pp_later.gt(0)
    )
    return result


def build_cross_grid_effects(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, group in summary.groupby(
        ["rule", "period", "condition", "value"], observed=True, sort=True
    ):
        rows.append({
            "rule": key[0], "period": key[1], "condition": key[2], "value": key[3],
            "configurations": len(group),
            "median_entries": group.entries.median(),
            "median_entry_share_pct": (group.entries / group.overall_entries * 100).median(),
            "configs_positive_mean": int(group.return_24h_mean_pct.gt(0).sum()),
            "configs_positive_median": int(group.return_24h_median_pct.gt(0).sum()),
            "configs_mean_beats_complement": int(group.mean_advantage_vs_complement_pp.gt(0).sum()),
            "median_mean_advantage_vs_complement_pp": group.mean_advantage_vs_complement_pp.median(),
            "median_mfe_mae_ratio": group.mfe_mae_ratio.median(),
        })
    return pd.DataFrame(rows)
