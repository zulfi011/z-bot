from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

TIMEFRAMES = [
    "1m",
    "3m",
    "5m",
]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")


GROUP_COLUMNS = [
    "asset",
    "timeframe",
    "average_type",
    "touch_zone",
    "market_regime",
]


FORWARD_RETURN_COLUMNS = [
    "return_5m_pct",
    "return_15m_pct",
    "return_30m_pct",
    "return_1h_pct",
    "return_4h_pct",
    "return_24h_pct",
]


def safe_pct(
    numerator: int,
    denominator: int,
):
    if denominator == 0:
        return np.nan

    return (
        numerator
        / denominator
        * 100
    )


def load_and_attach_regime(
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:

    outcome_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_trailing_research.parquet"
    )

    regime_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_regime.parquet"
    )

    if not outcome_file.exists():
        raise FileNotFoundError(
            f"Missing: {outcome_file}"
        )

    if not regime_file.exists():
        raise FileNotFoundError(
            f"Missing: {regime_file}"
        )

    # ---------------------------------------------------------
    # Main outcome dataset
    # ---------------------------------------------------------

    df = pd.read_parquet(
        outcome_file
    )

    # ---------------------------------------------------------
    # Regime lookup
    # ---------------------------------------------------------

    regime = pd.read_parquet(
        regime_file,
        columns=[
            "event_id",
            "market_regime",
        ],
    )

    if regime[
        "event_id"
    ].duplicated().any():

        raise ValueError(
            f"{symbol} {timeframe}: "
            "duplicate event_id in regime data"
        )

    original_rows = len(
        df
    )

    df = df.merge(
        regime,
        on="event_id",
        how="left",
        validate="one_to_one",
    )

    if len(
        df
    ) != original_rows:

        raise ValueError(
            f"{symbol} {timeframe}: "
            "row count changed during regime merge"
        )

    return df


def summarize_group(
    group: pd.DataFrame,
) -> dict:

    result = {}

    # =========================================================
    # EVENT COUNT
    # =========================================================

    result[
        "event_count"
    ] = len(
        group
    )

    # =========================================================
    # FORWARD RETURNS
    #
    # Include medians because Part 20 explicitly asks whether
    # returns change between regimes.
    # =========================================================

    for column in FORWARD_RETURN_COLUMNS:

        result[
            f"median_{column}"
        ] = (
            group[
                column
            ]
            .median()
        )

        result[
            f"mean_{column}"
        ] = (
            group[
                column
            ]
            .mean()
        )

        result[
            f"valid_{column}_count"
        ] = (
            group[
                column
            ]
            .notna()
            .sum()
        )

    # =========================================================
    # +2.5% PROFIT REACH
    #
    # Valid:
    # True/False reached observations.
    #
    # Unknown:
    # NA due to incomplete future observation.
    # =========================================================

    reach = group[
        "reached_2_5_pct"
    ]

    valid_reach = reach.notna()

    reach_valid_count = int(
        valid_reach.sum()
    )

    reached_count = int(
        (
            reach
            == True
        ).sum()
    )

    result[
        "reach_2_5_valid_count"
    ] = reach_valid_count

    result[
        "reach_2_5_count"
    ] = reached_count

    result[
        "reach_2_5_probability_pct"
    ] = safe_pct(
        reached_count,
        reach_valid_count,
    )

    reached_rows = group[
        reach
        == True
    ]

    result[
        "median_time_to_2_5_minutes"
    ] = (
        reached_rows[
            "time_to_2_5_pct_minutes"
        ]
        .median()
    )

    # =========================================================
    # 24H MAE
    # =========================================================

    mae_valid = group[
        "downside_window_complete_24h"
    ].fillna(False)

    mae = group.loc[
        mae_valid,
        "max_downside_24h_pct",
    ]

    result[
        "mae_24h_valid_count"
    ] = len(
        mae
    )

    result[
        "mae_24h_median_pct"
    ] = mae.median()

    result[
        "mae_24h_p10_pct"
    ] = (
        mae.quantile(
            0.10
        )
        if len(mae)
        else np.nan
    )

    result[
        "mae_24h_p05_pct"
    ] = (
        mae.quantile(
            0.05
        )
        if len(mae)
        else np.nan
    )

    result[
        "mae_24h_worst_pct"
    ] = (
        mae.min()
        if len(mae)
        else np.nan
    )

    # =========================================================
    # 24H MFE
    # =========================================================

    mfe_valid = group[
        "upside_window_complete_24h"
    ].fillna(False)

    mfe = group.loc[
        mfe_valid,
        "max_upside_24h_pct",
    ]

    result[
        "mfe_24h_valid_count"
    ] = len(
        mfe
    )

    result[
        "mfe_24h_median_pct"
    ] = mfe.median()

    result[
        "mfe_24h_p75_pct"
    ] = (
        mfe.quantile(
            0.75
        )
        if len(mfe)
        else np.nan
    )

    result[
        "mfe_24h_p90_pct"
    ] = (
        mfe.quantile(
            0.90
        )
        if len(mfe)
        else np.nan
    )

    result[
        "mfe_24h_p95_pct"
    ] = (
        mfe.quantile(
            0.95
        )
        if len(mfe)
        else np.nan
    )

    # =========================================================
    # MFE / MAE BALANCE
    #
    # Use medians from the same regime group.
    # =========================================================

    median_mae = (
        result[
            "mae_24h_median_pct"
        ]
    )

    median_mfe = (
        result[
            "mfe_24h_median_pct"
        ]
    )

    if (
        pd.notna(
            median_mae
        )
        and median_mae != 0
        and pd.notna(
            median_mfe
        )
    ):

        result[
            "median_mfe_mae_ratio"
        ] = (
            median_mfe
            / abs(
                median_mae
            )
        )

        result[
            "median_excursion_balance_pct"
        ] = (
            median_mfe
            + median_mae
        )

    else:

        result[
            "median_mfe_mae_ratio"
        ] = np.nan

        result[
            "median_excursion_balance_pct"
        ] = np.nan

    # =========================================================
    # +2.5 TARGET VS -2.5 STOP
    # =========================================================

    outcome = group[
        "target_2_5_vs_stop_2_5_outcome"
    ].astype(
        "string"
    )

    target_first = int(
        (
            outcome
            == "target_first"
        ).sum()
    )

    stop_first = int(
        (
            outcome
            == "stop_first"
        ).sum()
    )

    ambiguous = int(
        (
            outcome
            == "same_candle_ambiguous"
        ).sum()
    )

    neither = int(
        (
            outcome
            == "neither"
        ).sum()
    )

    incomplete = int(
        (
            outcome
            == "incomplete_unknown"
        ).sum()
    )

    confirmed = (
        target_first
        + stop_first
        + ambiguous
        + neither
    )

    decisive = (
        target_first
        + stop_first
    )

    result[
        "first_hit_target_count"
    ] = target_first

    result[
        "first_hit_stop_count"
    ] = stop_first

    result[
        "first_hit_ambiguous_count"
    ] = ambiguous

    result[
        "first_hit_neither_count"
    ] = neither

    result[
        "first_hit_incomplete_count"
    ] = incomplete

    result[
        "first_hit_confirmed_count"
    ] = confirmed

    result[
        "target_first_all_confirmed_pct"
    ] = safe_pct(
        target_first,
        confirmed,
    )

    result[
        "target_first_decisive_pct"
    ] = safe_pct(
        target_first,
        decisive,
    )

    # =========================================================
    # POST-ACTIVATION +2.5% CONTINUATION
    # =========================================================

    activated = group[
        "trailing_activation_reached"
    ].fillna(False)

    activated_count = int(
        activated.sum()
    )

    result[
        "activated_2_5_count"
    ] = activated_count

    post_valid = (
        activated
        &
        group[
            "post_activation_window_complete_24h"
        ].fillna(False)
    )

    post = group[
        post_valid
    ]

    result[
        "post_activation_24h_valid_count"
    ] = len(
        post
    )

    result[
        "post_activation_median_extra_upside_24h_pct"
    ] = (
        post[
            "extra_upside_after_activation_24h_pct"
        ]
        .median()
    )

    result[
        "post_activation_median_retracement_24h_pct"
    ] = (
        post[
            "max_retracement_from_peak_24h_pct"
        ]
        .median()
    )

    result[
        "post_activation_median_time_to_peak_24h_minutes"
    ] = (
        post[
            "time_to_post_activation_peak_24h_minutes"
        ]
        .median()
    )

    # =========================================================
    # 30% PROFIT GIVEBACK TRAILING
    #
    # We do NOT pretend ambiguous candles have a precise exit.
    #
    # For resolved exits:
    # trail_30_old_locked_profit_pct is the profit locked by
    # the already-active trail at the start of the candle.
    # =========================================================

    trail_outcome = group[
        "trail_30_outcome"
    ].astype(
        "string"
    )

    trail_resolved = (
        trail_outcome
        == "triggered_resolved"
    )

    trail_ambiguous = (
        trail_outcome
        == "ambiguous_same_candle"
    )

    trail_no_trigger = (
        trail_outcome
        == "no_trigger"
    )

    trail_incomplete = (
        trail_outcome
        == "incomplete_unknown"
    )

    resolved_count = int(
        trail_resolved.sum()
    )

    ambiguous_count = int(
        trail_ambiguous.sum()
    )

    no_trigger_count = int(
        trail_no_trigger.sum()
    )

    incomplete_count = int(
        trail_incomplete.sum()
    )

    trail_known = (
        resolved_count
        + ambiguous_count
        + no_trigger_count
    )

    result[
        "trail30_resolved_count"
    ] = resolved_count

    result[
        "trail30_ambiguous_count"
    ] = ambiguous_count

    result[
        "trail30_no_trigger_count"
    ] = no_trigger_count

    result[
        "trail30_incomplete_count"
    ] = incomplete_count

    result[
        "trail30_resolved_pct"
    ] = safe_pct(
        resolved_count,
        trail_known,
    )

    result[
        "trail30_ambiguous_pct"
    ] = safe_pct(
        ambiguous_count,
        trail_known,
    )

    result[
        "trail30_no_trigger_pct"
    ] = safe_pct(
        no_trigger_count,
        trail_known,
    )

    resolved_trails = group[
        trail_resolved
    ]

    result[
        "trail30_median_locked_profit_pct"
    ] = (
        resolved_trails[
            "trail_30_old_locked_profit_pct"
        ]
        .median()
    )

    result[
        "trail30_mean_locked_profit_pct"
    ] = (
        resolved_trails[
            "trail_30_old_locked_profit_pct"
        ]
        .mean()
    )

    result[
        "trail30_median_time_minutes"
    ] = (
        resolved_trails[
            "trail_30_time_minutes"
        ]
        .median()
    )

    return result


def main():

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_frames = []

    # ---------------------------------------------------------
    # Load all 9 event datasets and attach regime
    # ---------------------------------------------------------

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            print(
                f"Loading {symbol} {timeframe}"
            )

            df = load_and_attach_regime(
                symbol,
                timeframe,
            )

            # Regime unavailable means one or more averages
            # were not yet available.
            df = df[
                df[
                    "market_regime"
                ].notna()
            ].copy()

            all_frames.append(
                df
            )

    data = pd.concat(
        all_frames,
        ignore_index=True,
    )

    print(
        f"\nClassified event rows loaded: {len(data):,}"
    )

    # ---------------------------------------------------------
    # Build full regime comparison
    #
    # 3 assets
    # x 3 timeframes
    # x 3 averages
    # x 3 zones
    # x 3 regimes
    #
    # Maximum expected = 243 rows
    # assuming every combination exists.
    # ---------------------------------------------------------

    rows = []

    grouped = data.groupby(
        GROUP_COLUMNS,
        dropna=False,
        sort=True,
    )

    for keys, group in grouped:

        row = dict(
            zip(
                GROUP_COLUMNS,
                keys,
            )
        )

        row.update(
            summarize_group(
                group
            )
        )

        rows.append(
            row
        )

    comparison = pd.DataFrame(
        rows
    )

    output_file = (
        RESULTS_DIR
        / "regime_comparison_master.csv"
    )

    comparison.to_csv(
        output_file,
        index=False,
    )

    # ---------------------------------------------------------
    # Primary candidate:
    # SOL / 5m / 15D / 0.5%
    # ---------------------------------------------------------

    primary = comparison[
        (
            comparison[
                "asset"
            ]
            == "SOLUSDT"
        )
        &
        (
            comparison[
                "timeframe"
            ]
            == "5m"
        )
        &
        (
            comparison[
                "average_type"
            ]
            .astype(str)
            .str.lower()
            == "15d"
        )
        &
        (
            np.isclose(
                comparison[
                    "touch_zone"
                ].astype(float),
                0.5,
            )
        )
    ].copy()

    primary_file = (
        RESULTS_DIR
        / "regime_primary_setup_comparison.csv"
    )

    primary.to_csv(
        primary_file,
        index=False,
    )

    # ---------------------------------------------------------
    # Overall regime summary
    #
    # Median of setup-level statistics.
    # Do NOT pool millions of correlated touch rows together
    # for the high-level comparison.
    # ---------------------------------------------------------

    overall_metrics = [
        "event_count",

        "median_return_5m_pct",
        "median_return_15m_pct",
        "median_return_30m_pct",
        "median_return_1h_pct",
        "median_return_4h_pct",
        "median_return_24h_pct",

        "reach_2_5_probability_pct",
        "median_time_to_2_5_minutes",

        "mae_24h_median_pct",
        "mfe_24h_median_pct",
        "median_mfe_mae_ratio",
        "median_excursion_balance_pct",

        "target_first_all_confirmed_pct",
        "target_first_decisive_pct",

        "post_activation_median_extra_upside_24h_pct",
        "post_activation_median_retracement_24h_pct",

        "trail30_resolved_pct",
        "trail30_ambiguous_pct",
        "trail30_no_trigger_pct",
        "trail30_median_locked_profit_pct",
    ]

    overall = (
        comparison
        .groupby(
            "market_regime"
        )[
            overall_metrics
        ]
        .median()
        .reset_index()
    )

    overall_file = (
        RESULTS_DIR
        / "regime_overall_comparison.csv"
    )

    overall.to_csv(
        overall_file,
        index=False,
    )

    # ---------------------------------------------------------
    # Asset-level regime comparison
    # ---------------------------------------------------------

    by_asset = (
        comparison
        .groupby(
            [
                "asset",
                "market_regime",
            ]
        )[
            overall_metrics
        ]
        .median()
        .reset_index()
    )

    by_asset_file = (
        RESULTS_DIR
        / "regime_comparison_by_asset.csv"
    )

    by_asset.to_csv(
        by_asset_file,
        index=False,
    )

    print(
        "\nSaved:"
    )

    print(
        output_file
    )

    print(
        overall_file
    )

    print(
        by_asset_file
    )

    print(
        primary_file
    )

    # ---------------------------------------------------------
    # Display overall comparison
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 125
    )

    print(
        "OVERALL REGIME COMPARISON"
    )

    print(
        "=" * 125
    )

    display_overall = [
        "market_regime",
        "event_count",
        "median_return_1h_pct",
        "median_return_4h_pct",
        "median_return_24h_pct",
        "reach_2_5_probability_pct",
        "mae_24h_median_pct",
        "mfe_24h_median_pct",
        "median_mfe_mae_ratio",
        "target_first_decisive_pct",
        "post_activation_median_extra_upside_24h_pct",
        "trail30_median_locked_profit_pct",
    ]

    print(
        overall[
            display_overall
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Display by asset
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 125
    )

    print(
        "REGIME COMPARISON BY ASSET"
    )

    print(
        "=" * 125
    )

    display_asset = [
        "asset",
        "market_regime",
        "event_count",
        "median_return_24h_pct",
        "reach_2_5_probability_pct",
        "mae_24h_median_pct",
        "mfe_24h_median_pct",
        "median_mfe_mae_ratio",
        "target_first_decisive_pct",
        "post_activation_median_extra_upside_24h_pct",
        "trail30_median_locked_profit_pct",
    ]

    print(
        by_asset[
            display_asset
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Primary candidate
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 125
    )

    print(
        "PRIMARY SETUP — SOL / 15D / 5m / 0.5%"
    )

    print(
        "=" * 125
    )

    primary_columns = [
        "market_regime",
        "event_count",

        "median_return_5m_pct",
        "median_return_15m_pct",
        "median_return_30m_pct",
        "median_return_1h_pct",
        "median_return_4h_pct",
        "median_return_24h_pct",

        "reach_2_5_probability_pct",
        "median_time_to_2_5_minutes",

        "mae_24h_median_pct",
        "mae_24h_p10_pct",

        "mfe_24h_median_pct",
        "mfe_24h_p90_pct",

        "median_mfe_mae_ratio",
        "median_excursion_balance_pct",

        "target_first_all_confirmed_pct",
        "target_first_decisive_pct",

        "post_activation_median_extra_upside_24h_pct",
        "post_activation_median_retracement_24h_pct",

        "trail30_resolved_pct",
        "trail30_ambiguous_pct",
        "trail30_no_trigger_pct",
        "trail30_median_locked_profit_pct",
    ]

    print(
        primary[
            primary_columns
        ].sort_values(
            "market_regime"
        ).to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()