from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("results/tables")

INPUT_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)

OUTPUT_FILE = (
    RESULTS_DIR
    / "average_consistency_comparison.csv"
)


METRICS = {
    "reach_probability_pct": {
        "direction": "higher",
        "label": "+2.5% reach",
    },
    "mae_24h_median_pct": {
        "direction": "higher",
        "label": "24h median MAE",
    },
    "mfe_24h_median_pct": {
        "direction": "higher",
        "label": "24h median MFE",
    },
    "median_mfe_mae_ratio": {
        "direction": "higher",
        "label": "MFE/MAE ratio",
    },
    "target_2_5_first_vs_stop_2_5_pct": {
        "direction": "higher",
        "label": "+2.5 vs -2.5 first-hit",
    },
    "post_activation_median_extra_upside_24h_pct": {
        "direction": "higher",
        "label": "post-activation continuation",
    },
    "trail30_median_realized_return_pct": {
        "direction": "higher",
        "label": "30% trail realized return",
    },
}


def build_average_asset_summary(
    master: pd.DataFrame,
) -> pd.DataFrame:

    metric_columns = list(
        METRICS.keys()
    )

    summary = (
        master
        .groupby(
            [
                "asset",
                "average_type",
            ]
        )[
            metric_columns
            + [
                "event_count"
            ]
        ]
        .median()
        .reset_index()
    )

    return summary


def add_metric_ranks(
    summary: pd.DataFrame,
) -> pd.DataFrame:

    output = summary.copy()

    for metric, config in METRICS.items():

        ascending = (
            config[
                "direction"
            ]
            != "higher"
        )

        rank_column = (
            f"{metric}_rank"
        )

        output[
            rank_column
        ] = (
            output
            .groupby(
                "asset"
            )[
                metric
            ]
            .rank(
                method="min",
                ascending=ascending,
            )
        )

    return output


def calculate_asset_wins(
    ranked: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for asset in sorted(
        ranked[
            "asset"
        ].unique()
    ):

        subset = ranked[
            ranked[
                "asset"
            ]
            == asset
        ]

        for average_type in [
            "7d",
            "15d",
            "30d",
        ]:

            row = subset[
                subset[
                    "average_type"
                ]
                == average_type
            ]

            if row.empty:
                continue

            wins = 0
            seconds = 0
            thirds = 0

            rank_values = []

            for metric in METRICS:

                rank_column = (
                    f"{metric}_rank"
                )

                rank = float(
                    row[
                        rank_column
                    ].iloc[0]
                )

                rank_values.append(
                    rank
                )

                if rank == 1:
                    wins += 1

                elif rank == 2:
                    seconds += 1

                elif rank == 3:
                    thirds += 1

            rows.append(
                {
                    "asset": asset,
                    "average_type": average_type,
                    "metric_wins": wins,
                    "metric_second_places": seconds,
                    "metric_third_places": thirds,
                    "mean_metric_rank": (
                        sum(
                            rank_values
                        )
                        / len(
                            rank_values
                        )
                    ),
                }
            )

    return pd.DataFrame(
        rows
    )


def calculate_timeframe_consistency(
    master: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for asset in sorted(
        master[
            "asset"
        ].unique()
    ):

        asset_df = master[
            master[
                "asset"
            ]
            == asset
        ]

        for average_type in [
            "7d",
            "15d",
            "30d",
        ]:

            subset = asset_df[
                asset_df[
                    "average_type"
                ]
                == average_type
            ]

            for metric in METRICS:

                timeframe_medians = (
                    subset
                    .groupby(
                        "timeframe"
                    )[
                        metric
                    ]
                    .median()
                )

                mean_value = (
                    timeframe_medians.mean()
                )

                min_value = (
                    timeframe_medians.min()
                )

                max_value = (
                    timeframe_medians.max()
                )

                spread = (
                    max_value
                    - min_value
                )

                if mean_value != 0:

                    relative_spread_pct = (
                        abs(
                            spread
                        )
                        / abs(
                            mean_value
                        )
                        * 100
                    )

                else:

                    relative_spread_pct = None

                rows.append(
                    {
                        "asset": asset,
                        "average_type": average_type,
                        "metric": metric,

                        "1m_value": (
                            timeframe_medians.get(
                                "1m"
                            )
                        ),

                        "3m_value": (
                            timeframe_medians.get(
                                "3m"
                            )
                        ),

                        "5m_value": (
                            timeframe_medians.get(
                                "5m"
                            )
                        ),

                        "timeframe_mean": (
                            mean_value
                        ),

                        "timeframe_spread": (
                            spread
                        ),

                        "relative_spread_pct": (
                            relative_spread_pct
                        ),
                    }
                )

    return pd.DataFrame(
        rows
    )


def calculate_zone_consistency(
    master: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for asset in sorted(
        master[
            "asset"
        ].unique()
    ):

        asset_df = master[
            master[
                "asset"
            ]
            == asset
        ]

        for average_type in [
            "7d",
            "15d",
            "30d",
        ]:

            subset = asset_df[
                asset_df[
                    "average_type"
                ]
                == average_type
            ]

            for metric in METRICS:

                zone_medians = (
                    subset
                    .groupby(
                        "touch_zone"
                    )[
                        metric
                    ]
                    .median()
                )

                mean_value = (
                    zone_medians.mean()
                )

                spread = (
                    zone_medians.max()
                    - zone_medians.min()
                )

                if mean_value != 0:

                    relative_spread_pct = (
                        abs(
                            spread
                        )
                        / abs(
                            mean_value
                        )
                        * 100
                    )

                else:

                    relative_spread_pct = None

                rows.append(
                    {
                        "asset": asset,
                        "average_type": average_type,
                        "metric": metric,

                        "zone_0_5_value": (
                            zone_medians.get(
                                0.5
                            )
                        ),

                        "zone_1_0_value": (
                            zone_medians.get(
                                1.0
                            )
                        ),

                        "zone_1_5_value": (
                            zone_medians.get(
                                1.5
                            )
                        ),

                        "zone_mean": (
                            mean_value
                        ),

                        "zone_spread": (
                            spread
                        ),

                        "relative_spread_pct": (
                            relative_spread_pct
                        ),
                    }
                )

    return pd.DataFrame(
        rows
    )


def calculate_overall_average_summary(
    master: pd.DataFrame,
) -> pd.DataFrame:

    metric_columns = list(
        METRICS.keys()
    )

    overall = (
        master
        .groupby(
            "average_type"
        )[
            metric_columns
            + [
                "event_count"
            ]
        ]
        .median()
        .reset_index()
    )

    for metric in METRICS:

        overall[
            f"{metric}_rank"
        ] = (
            overall[
                metric
            ]
            .rank(
                method="min",
                ascending=False,
            )
        )

    rank_columns = [
        f"{metric}_rank"
        for metric
        in METRICS
    ]

    overall[
        "metric_wins"
    ] = (
        overall[
            rank_columns
        ]
        .eq(
            1
        )
        .sum(
            axis=1
        )
    )

    overall[
        "mean_metric_rank"
    ] = (
        overall[
            rank_columns
        ]
        .mean(
            axis=1
        )
    )

    return overall


def main():

    master = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Loaded master comparison:"
    )

    print(
        f"Rows: {len(master)}"
    )

    # ---------------------------------------------------------
    # Asset-level average summaries
    # ---------------------------------------------------------

    asset_summary = (
        build_average_asset_summary(
            master
        )
    )

    ranked_asset_summary = (
        add_metric_ranks(
            asset_summary
        )
    )

    asset_wins = (
        calculate_asset_wins(
            ranked_asset_summary
        )
    )

    # ---------------------------------------------------------
    # Consistency calculations
    # ---------------------------------------------------------

    timeframe_consistency = (
        calculate_timeframe_consistency(
            master
        )
    )

    zone_consistency = (
        calculate_zone_consistency(
            master
        )
    )

    overall_summary = (
        calculate_overall_average_summary(
            master
        )
    )

    # ---------------------------------------------------------
    # Save a single combined comparison file
    # ---------------------------------------------------------

    combined = ranked_asset_summary.merge(
        asset_wins,
        on=[
            "asset",
            "average_type",
        ],
        how="left",
        validate="one_to_one",
    )

    combined.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    timeframe_file = (
        RESULTS_DIR
        / "average_timeframe_consistency.csv"
    )

    timeframe_consistency.to_csv(
        timeframe_file,
        index=False,
    )

    zone_file = (
        RESULTS_DIR
        / "average_zone_consistency.csv"
    )

    zone_consistency.to_csv(
        zone_file,
        index=False,
    )

    overall_file = (
        RESULTS_DIR
        / "average_overall_summary.csv"
    )

    overall_summary.to_csv(
        overall_file,
        index=False,
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        timeframe_file
    )

    print(
        zone_file
    )

    print(
        overall_file
    )

    # ---------------------------------------------------------
    # Print asset-level winners
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 110
    )

    print(
        "AVERAGE COMPARISON BY ASSET"
    )

    print(
        "=" * 110
    )

    display_columns = [
        "asset",
        "average_type",
        "event_count",

        "reach_probability_pct",
        "mae_24h_median_pct",
        "mfe_24h_median_pct",
        "median_mfe_mae_ratio",
        "target_2_5_first_vs_stop_2_5_pct",
        "post_activation_median_extra_upside_24h_pct",
        "trail30_median_realized_return_pct",

        "metric_wins",
        "mean_metric_rank",
    ]

    print(
        combined[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Overall comparison
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 110
    )

    print(
        "OVERALL 7D VS 15D VS 30D"
    )

    print(
        "=" * 110
    )

    overall_display = [
        "average_type",
        "event_count",
        "reach_probability_pct",
        "mae_24h_median_pct",
        "mfe_24h_median_pct",
        "median_mfe_mae_ratio",
        "target_2_5_first_vs_stop_2_5_pct",
        "post_activation_median_extra_upside_24h_pct",
        "trail30_median_realized_return_pct",
        "metric_wins",
        "mean_metric_rank",
    ]

    print(
        overall_summary[
            overall_display
        ]
        .sort_values(
            "mean_metric_rank"
        )
        .to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()