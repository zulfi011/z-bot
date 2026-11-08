"""Event-population statistics preserving Stage 1 timing and denominators."""

import numpy as np
import pandas as pd

HORIZONS = ["5m", "15m", "30m", "1h", "4h", "24h"]
WINDOWS = ["1h", "4h", "24h"]
TARGETS = ["0_5", "1_0", "1_5", "2_0", "2_5", "3_0", "5_0"]
STOPS = ["1_0", "1_5", "2_0", "2_5", "3_0"]
TRAILS = ["10", "20", "30", "40", "50"]
FIRST_OUTCOMES = ["target_first", "stop_first", "same_candle_ambiguous", "neither", "incomplete_unknown"]
TRAIL_OUTCOMES = ["triggered_resolved", "ambiguous_same_candle", "not_triggered_24h", "incomplete_unknown"]


def required_columns() -> list[str]:
    columns = ["event_id", "asset", "timeframe", "average_type", "touch_zone", "timestamp",
               "observation_complete_24h", "trailing_activation_reached"]
    columns += [f"return_{h}_pct" for h in HORIZONS]
    for target in TARGETS:
        columns += [f"reached_{target}_pct", f"time_to_{target}_pct_minutes"]
    for window in WINDOWS:
        columns += [f"{side}_window_complete_{window}" for side in ["downside", "upside"]]
        columns += [f"max_{side}_{window}_pct" for side in ["downside", "upside"]]
        columns += [f"post_activation_window_complete_{window}",
                    f"extra_upside_after_activation_{window}_pct"]
    columns += [f"target_2_5_vs_stop_{s}_outcome" for s in STOPS]
    for trail in TRAILS:
        columns += [f"trail_{trail}_outcome", f"trail_{trail}_old_locked_profit_pct",
                    f"trail_{trail}_time_minutes"]
    return columns


def pct(numerator: int, denominator: int) -> float:
    return numerator / denominator * 100 if denominator else np.nan


def summarize(group: pd.DataFrame) -> dict:
    """All populations use the same formulas; never fill unknown outcomes with zero."""
    row = {"forward_return_total_event_count": len(group),
           "complete_24h_event_count": int(group.observation_complete_24h.sum())}
    for horizon in HORIZONS:
        values = group[f"return_{horizon}_pct"].dropna()
        row.update({f"return_{horizon}_valid_count": len(values),
                    f"return_{horizon}_median_pct": values.median(),
                    f"return_{horizon}_mean_pct": values.mean()})
    for target in TARGETS:
        reached = group[f"reached_{target}_pct"].astype("boolean")
        hits = reached.fillna(False)
        valid = int(reached.notna().sum())
        row.update({f"target_{target}_valid_count": valid,
                    f"target_{target}_reached_count": int(hits.sum()),
                    f"target_{target}_unknown_count": int(reached.isna().sum()),
                    f"target_{target}_reach_pct": pct(int(hits.sum()), valid),
                    f"target_{target}_median_minutes": group.loc[hits, f"time_to_{target}_pct_minutes"].median()})
    # Stage 1 event_count is the +2.5% confirmed target count, including any
    # confirmed hits in incomplete windows. Keep complete-window count separate.
    row["event_count"] = row["target_2_5_valid_count"]
    row["reach_probability_pct"] = row["target_2_5_reach_pct"]
    row["median_time_to_target_minutes"] = row["target_2_5_median_minutes"]
    for window in WINDOWS:
        for side, label in [("downside", "mae"), ("upside", "mfe")]:
            mask = group[f"{side}_window_complete_{window}"].fillna(False).astype(bool)
            values = group.loc[mask, f"max_{side}_{window}_pct"].dropna()
            row.update({f"{label}_{window}_valid_count": len(values),
                        f"{label}_{window}_median_pct": values.median(),
                        f"{label}_{window}_mean_pct": values.mean()})
            if label == "mae":
                row.update({f"mae_{window}_severe10_pct": values.quantile(.1),
                            f"mae_{window}_severe5_pct": values.quantile(.05),
                            f"mae_{window}_worst_pct": values.min()})
            else:
                for q in [75, 90, 95]:
                    row[f"mfe_{window}_p{q}_pct"] = values.quantile(q / 100)
                row[f"mfe_{window}_best_pct"] = values.max()
    mae, mfe = row["mae_24h_median_pct"], row["mfe_24h_median_pct"]
    row["median_mfe_mae_ratio"] = mfe / abs(mae) if mae != 0 else np.nan
    row["median_excursion_balance_pct"] = mfe - abs(mae)
    for stop in STOPS:
        outcomes = group[f"target_2_5_vs_stop_{stop}_outcome"]
        if not outcomes.isin(FIRST_OUTCOMES).all():
            raise ValueError("Unknown first-hit outcome")
        counts = outcomes.value_counts()
        for outcome in FIRST_OUTCOMES:
            row[f"first_{stop}_{outcome}_count"] = int(counts.get(outcome, 0))
        confirmed = int(outcomes.ne("incomplete_unknown").sum())
        target = int(counts.get("target_first", 0))
        decisive = target + int(counts.get("stop_first", 0))
        row.update({f"first_{stop}_confirmed_count": confirmed,
                    f"first_{stop}_decisive_count": decisive,
                    f"target_2_5_first_vs_stop_{stop}_pct": pct(target, confirmed),
                    f"first_{stop}_target_first_decisive_pct": pct(target, decisive)})
    activated = group.loc[group.trailing_activation_reached.fillna(False).astype(bool)]
    row["activated_event_count"] = len(activated)
    for window in WINDOWS:
        mask = activated[f"post_activation_window_complete_{window}"].fillna(False).astype(bool)
        values = activated.loc[mask, f"extra_upside_after_activation_{window}_pct"].dropna()
        row[f"post_activation_{window}_valid_count"] = len(values)
        row[f"post_activation_median_extra_upside_{window}_pct"] = values.median()
    for trail in TRAILS:
        outcomes = activated[f"trail_{trail}_outcome"]
        if not outcomes.isin(TRAIL_OUTCOMES).all():
            raise ValueError("Unknown trailing outcome")
        counts = outcomes.value_counts()
        confirmed = int(outcomes.ne("incomplete_unknown").sum())
        resolved = outcomes.eq("triggered_resolved")
        values = activated.loc[resolved, f"trail_{trail}_old_locked_profit_pct"].dropna()
        row[f"trail{trail}_confirmed_count"] = confirmed
        for outcome in TRAIL_OUTCOMES:
            row[f"trail{trail}_{outcome}_count"] = int(counts.get(outcome, 0))
        for outcome, label in [("triggered_resolved", "resolved"),
                               ("ambiguous_same_candle", "ambiguous"),
                               ("not_triggered_24h", "not_triggered_24h")]:
            row[f"trail{trail}_{label}_pct"] = pct(int(counts.get(outcome, 0)), confirmed)
        row[f"trail{trail}_median_realized_return_pct"] = values.median()
        row[f"trail{trail}_mean_realized_return_pct"] = values.mean()
        row[f"trail{trail}_median_time_to_exit_minutes"] = activated.loc[resolved, f"trail_{trail}_time_minutes"].median()
    return row
