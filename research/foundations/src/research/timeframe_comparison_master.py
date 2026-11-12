from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("results/tables")

INPUT_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)

OUTPUT_OVERALL = (
    RESULTS_DIR
    / "timeframe_comparison_overall.csv"
)

OUTPUT_ASSET = (
    RESULTS_DIR
    / "timeframe_comparison_by_asset.csv"
)

OUTPUT_15D = (
    RESULTS_DIR
    / "timeframe_comparison_15d.csv"
)


QUALITY_METRICS = [
    "reach_probability_pct",
    "mae_24h_median_pct",
    "mfe_24h_median_pct",
    "median_mfe_mae_ratio",
    "target_2_5_first_vs_stop_2_5_pct",
    "post_activation_median_extra_upside_24h_pct",
    "trail30_median_realized_return_pct",
]


def add_ranks(
    df: pd.DataFrame,
    group_columns=None,
) -> pd.DataFrame:

    output = df.copy()

    for metric in QUALITY_METRICS:

        rank_column = (
            f"{metric}_rank"
        )

        if group_columns:

            output[
                rank_column
            ] = (
                output
                .groupby(
                    group_columns
                )[metric]
                .rank(
                    method="min",
                    ascending=False,
                )
            )

        else:

            output[
                rank_column
            ] = (
                output[
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
        in QUALITY_METRICS
    ]

    output[
        "metric_wins"
    ] = (
        output[
            rank_columns
        ]
        .eq(1)
        .sum(axis=1)
    )

    output[
        "mean_metric_rank"
    ] = (
        output[
            rank_columns
        ]
        .mean(axis=1)
    )

    return output


def calculate_relative_spread(
    df: pd.DataFrame,
    group_columns,
) -> pd.DataFrame:

    rows = []

    grouped = df.groupby(
        group_columns,
        dropna=False,
        sort=True,
    )

    for group_values, group in grouped:

        if not isinstance(
            group_values,
            tuple,
        ):
            group_values = (
                group_values,
            )

        base = dict(
            zip(
                group_columns,
                group_values,
            )
        )

        for metric in QUALITY_METRICS:

            values = (
                group[
                    metric
                ]
                .dropna()
                .astype(float)
            )

            if len(values) == 0:
                continue

            mean_value = (
                values.mean()
            )

            min_value = (
                values.min()
            )

            max_value = (
                values.max()
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
                    **base,
                    "metric": metric,
                    "min_value": min_value,
                    "max_value": max_value,
                    "spread": spread,
                    "mean_value": mean_value,
                    "relative_spread_pct": (
                        relative_spread_pct
                    ),
                }
            )

    return pd.DataFrame(
        rows
    )


def main():

    master = pd.read_csv(
        INPUT_FILE
    )

    print(
        "Loaded average comparison master"
    )

    print(
        f"Rows: {len(master)}"
    )

    # ---------------------------------------------------------
    # 18A.1 Overall timeframe comparison
    #
    # 27 setup rows per timeframe:
    # 3 assets x 3 averages x 3 zones
    # ---------------------------------------------------------

    overall = (
        master
        .groupby(
            "timeframe"
        )[
            QUALITY_METRICS
            + [
                "event_count"
            ]
        ]
        .median()
        .reset_index()
    )

    overall = add_ranks(
        overall
    )

    overall = (
        overall
        .sort_values(
            "mean_metric_rank"
        )
        .reset_index(
            drop=True
        )
    )

    overall.to_csv(
        OUTPUT_OVERALL,
        index=False,
    )

    # ---------------------------------------------------------
    # 18A.2 Comparison by asset
    #
    # 9 setup rows per asset/timeframe:
    # 3 averages x 3 zones
    # ---------------------------------------------------------

    by_asset = (
        master
        .groupby(
            [
                "asset",
                "timeframe",
            ]
        )[
            QUALITY_METRICS
            + [
                "event_count"
            ]
        ]
        .median()
        .reset_index()
    )

    by_asset = add_ranks(
        by_asset,
        group_columns=[
            "asset"
        ],
    )

    by_asset = (
        by_asset
        .sort_values(
            [
                "asset",
                "mean_metric_rank",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    by_asset.to_csv(
        OUTPUT_ASSET,
        index=False,
    )

    # ---------------------------------------------------------
    # 18A.3 15D-only comparison
    #
    # Part 17 identified 15D as our primary average candidate.
    #
    # 9 setup rows per timeframe:
    # 3 assets x 3 zones
    # ---------------------------------------------------------

    primary = master[
        master[
            "average_type"
        ]
        .astype(str)
        .str.lower()
        == "15d"
    ].copy()

    comparison_15d = (
        primary
        .groupby(
            "timeframe"
        )[
            QUALITY_METRICS
            + [
                "event_count"
            ]
        ]
        .median()
        .reset_index()
    )

    comparison_15d = add_ranks(
        comparison_15d
    )

    comparison_15d = (
        comparison_15d
        .sort_values(
            "mean_metric_rank"
        )
        .reset_index(
            drop=True
        )
    )

    comparison_15d.to_csv(
        OUTPUT_15D,
        index=False,
    )

    # ---------------------------------------------------------
    # 18A.4 Relative spread across 1m / 3m / 5m
    #
    # This tells us whether a "win" is actually meaningful.
    # ---------------------------------------------------------

    # calculate_relative_spread expects groups.
    # Overall only has 3 timeframe rows, so calculate directly.
    spread_rows = []

    for metric in QUALITY_METRICS:

        values = (
            overall[
                metric
            ]
            .astype(float)
        )

        mean_value = (
            values.mean()
        )

        spread = (
            values.max()
            - values.min()
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

        spread_rows.append(
            {
                "metric": metric,
                "min_value": values.min(),
                "max_value": values.max(),
                "spread": spread,
                "mean_value": mean_value,
                "relative_spread_pct": (
                    relative_spread_pct
                ),
            }
        )

    spread_df = pd.DataFrame(
        spread_rows
    )

    spread_file = (
        RESULTS_DIR
        / "timeframe_metric_spread.csv"
    )

    spread_df.to_csv(
        spread_file,
        index=False,
    )

    # ---------------------------------------------------------
    # Print outputs
    # ---------------------------------------------------------

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_OVERALL
    )

    print(
        OUTPUT_ASSET
    )

    print(
        OUTPUT_15D
    )

    print(
        spread_file
    )

    # ---------------------------------------------------------
    # Overall
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "OVERALL TIMEFRAME COMPARISON"
    )

    print(
        "=" * 120
    )

    display_columns = [
        "timeframe",
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
        overall[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # By asset
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "TIMEFRAME COMPARISON BY ASSET"
    )

    print(
        "=" * 120
    )

    print(
        by_asset[
            [
                "asset",
                "timeframe",
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
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # 15D only
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "15D PRIMARY AVERAGE — TIMEFRAME COMPARISON"
    )

    print(
        "=" * 120
    )

    print(
        comparison_15d[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Spread
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "RELATIVE SPREAD ACROSS 1m / 3m / 5m"
    )

    print(
        "=" * 120
    )

    print(
        spread_df[
            [
                "metric",
                "min_value",
                "max_value",
                "relative_spread_pct",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()