from pathlib import Path

import pandas as pd


RESULTS_DIR = Path("results/tables")

INPUT_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)

OUTPUT_OVERALL = (
    RESULTS_DIR
    / "asset_comparison_overall.csv"
)

OUTPUT_15D = (
    RESULTS_DIR
    / "asset_comparison_15d.csv"
)

OUTPUT_15D_5M = (
    RESULTS_DIR
    / "asset_comparison_15d_5m.csv"
)

OUTPUT_CONSISTENCY = (
    RESULTS_DIR
    / "asset_consistency.csv"
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
) -> pd.DataFrame:

    output = df.copy()

    for metric in QUALITY_METRICS:

        output[
            f"{metric}_rank"
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
        .sum(
            axis=1
        )
    )

    output[
        "mean_metric_rank"
    ] = (
        output[
            rank_columns
        ]
        .mean(
            axis=1
        )
    )

    return output


def build_asset_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:

    summary = (
        df
        .groupby(
            "asset"
        )[
            QUALITY_METRICS
            + [
                "event_count"
            ]
        ]
        .median()
        .reset_index()
    )

    summary = add_ranks(
        summary
    )

    summary = (
        summary
        .sort_values(
            "mean_metric_rank"
        )
        .reset_index(
            drop=True
        )
    )

    return summary


def build_consistency(
    master: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    for asset in sorted(
        master[
            "asset"
        ].unique()
    ):

        subset = master[
            master[
                "asset"
            ]
            == asset
        ]

        for metric in QUALITY_METRICS:

            values = (
                subset[
                    metric
                ]
                .dropna()
                .astype(float)
            )

            mean_value = (
                values.mean()
            )

            median_value = (
                values.median()
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
                    "asset": asset,
                    "metric": metric,
                    "mean_value": mean_value,
                    "median_value": median_value,
                    "min_value": min_value,
                    "max_value": max_value,
                    "spread": spread,
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
    # 19A.1 Overall asset comparison
    #
    # 27 setup rows per asset:
    # 3 timeframes x 3 averages x 3 zones
    # ---------------------------------------------------------

    overall = build_asset_summary(
        master
    )

    overall.to_csv(
        OUTPUT_OVERALL,
        index=False,
    )

    # ---------------------------------------------------------
    # 19A.2 15D-only comparison
    #
    # 9 setup rows per asset:
    # 3 timeframes x 3 zones
    # ---------------------------------------------------------

    primary_15d = master[
        master[
            "average_type"
        ]
        .astype(str)
        .str.lower()
        == "15d"
    ].copy()

    comparison_15d = (
        build_asset_summary(
            primary_15d
        )
    )

    comparison_15d.to_csv(
        OUTPUT_15D,
        index=False,
    )

    # ---------------------------------------------------------
    # 19A.3 15D + 5m comparison
    #
    # 3 setup rows per asset:
    # touch zones 0.5 / 1.0 / 1.5
    # ---------------------------------------------------------

    primary_15d_5m = master[
        (
            master[
                "average_type"
            ]
            .astype(str)
            .str.lower()
            == "15d"
        )
        &
        (
            master[
                "timeframe"
            ]
            == "5m"
        )
    ].copy()

    comparison_15d_5m = (
        build_asset_summary(
            primary_15d_5m
        )
    )

    comparison_15d_5m.to_csv(
        OUTPUT_15D_5M,
        index=False,
    )

    # ---------------------------------------------------------
    # 19A.4 Cross-setup consistency
    # ---------------------------------------------------------

    consistency = build_consistency(
        master
    )

    consistency.to_csv(
        OUTPUT_CONSISTENCY,
        index=False,
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_OVERALL
    )

    print(
        OUTPUT_15D
    )

    print(
        OUTPUT_15D_5M
    )

    print(
        OUTPUT_CONSISTENCY
    )

    # ---------------------------------------------------------
    # Overall output
    # ---------------------------------------------------------

    display_columns = [
        "asset",
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
        "\n"
        + "=" * 120
    )

    print(
        "OVERALL ASSET COMPARISON"
    )

    print(
        "=" * 120
    )

    print(
        overall[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # 15D output
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "15D PRIMARY AVERAGE — ASSET COMPARISON"
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
    # 15D + 5m output
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "15D + 5m PRIMARY CANDIDATE — ASSET COMPARISON"
    )

    print(
        "=" * 120
    )

    print(
        comparison_15d_5m[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Consistency summary
    # ---------------------------------------------------------

    consistency_summary = (
        consistency
        .groupby(
            "asset"
        )[
            "relative_spread_pct"
        ]
        .median()
        .reset_index()
        .sort_values(
            "relative_spread_pct"
        )
    )

    print(
        "\n"
        + "=" * 120
    )

    print(
        "ASSET CONSISTENCY ACROSS ALL SETUPS"
    )

    print(
        "=" * 120
    )

    print(
        consistency_summary.to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()