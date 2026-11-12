from pathlib import Path

import numpy as np
import pandas as pd


RESULTS_DIR = Path("results/tables")
REPORT_DIR = Path("results/reports")

MASTER_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)

OVERALL_FILE = (
    RESULTS_DIR
    / "timeframe_comparison_overall.csv"
)

ASSET_FILE = (
    RESULTS_DIR
    / "timeframe_comparison_by_asset.csv"
)

PRIMARY_15D_FILE = (
    RESULTS_DIR
    / "timeframe_comparison_15d.csv"
)

SPREAD_FILE = (
    RESULTS_DIR
    / "timeframe_metric_spread.csv"
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


def numeric_equal(
    left,
    right,
    rtol=1e-10,
    atol=1e-10,
):
    left = pd.to_numeric(
        left,
        errors="coerce",
    ).to_numpy(
        dtype=np.float64,
    )

    right = pd.to_numeric(
        right,
        errors="coerce",
    ).to_numpy(
        dtype=np.float64,
    )

    return bool(
        np.all(
            (
                np.isnan(left)
                & np.isnan(right)
            )
            |
            np.isclose(
                np.nan_to_num(left),
                np.nan_to_num(right),
                rtol=rtol,
                atol=atol,
            )
        )
    )


def validate_overall(
    master,
    overall,
):
    checks = {}

    expected = (
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

    checks[
        "overall_has_3_rows"
    ] = (
        len(overall) == 3
    )

    checks[
        "overall_timeframes_correct"
    ] = (
        set(
            overall[
                "timeframe"
            ]
        )
        == {
            "1m",
            "3m",
            "5m",
        }
    )

    merged = overall.merge(
        expected,
        on="timeframe",
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    for column in (
        QUALITY_METRICS
        + [
            "event_count"
        ]
    ):

        checks[
            f"overall_{column}_correct"
        ] = numeric_equal(
            merged[
                f"{column}_actual"
            ],
            merged[
                f"{column}_expected"
            ],
        )

    # Recalculate ranks
    expected_ranked = expected.copy()

    for metric in QUALITY_METRICS:

        expected_ranked[
            f"{metric}_rank"
        ] = (
            expected_ranked[
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

    expected_ranked[
        "metric_wins"
    ] = (
        expected_ranked[
            rank_columns
        ]
        .eq(1)
        .sum(
            axis=1
        )
    )

    expected_ranked[
        "mean_metric_rank"
    ] = (
        expected_ranked[
            rank_columns
        ]
        .mean(
            axis=1
        )
    )

    rank_merged = overall.merge(
        expected_ranked[
            [
                "timeframe",
                "metric_wins",
                "mean_metric_rank",
            ]
        ],
        on="timeframe",
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    checks[
        "overall_metric_wins_correct"
    ] = numeric_equal(
        rank_merged[
            "metric_wins_actual"
        ],
        rank_merged[
            "metric_wins_expected"
        ],
    )

    checks[
        "overall_mean_rank_correct"
    ] = numeric_equal(
        rank_merged[
            "mean_metric_rank_actual"
        ],
        rank_merged[
            "mean_metric_rank_expected"
        ],
    )

    return checks


def validate_by_asset(
    master,
    by_asset,
):
    checks = {}

    expected = (
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

    checks[
        "asset_table_has_9_rows"
    ] = (
        len(
            by_asset
        )
        == 9
    )

    merged = by_asset.merge(
        expected,
        on=[
            "asset",
            "timeframe",
        ],
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    for column in (
        QUALITY_METRICS
        + [
            "event_count"
        ]
    ):

        checks[
            f"asset_{column}_correct"
        ] = numeric_equal(
            merged[
                f"{column}_actual"
            ],
            merged[
                f"{column}_expected"
            ],
        )

    # Recalculate ranks within each asset
    expected_ranked = expected.copy()

    for metric in QUALITY_METRICS:

        expected_ranked[
            f"{metric}_rank"
        ] = (
            expected_ranked
            .groupby(
                "asset"
            )[
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

    expected_ranked[
        "metric_wins"
    ] = (
        expected_ranked[
            rank_columns
        ]
        .eq(1)
        .sum(
            axis=1
        )
    )

    expected_ranked[
        "mean_metric_rank"
    ] = (
        expected_ranked[
            rank_columns
        ]
        .mean(
            axis=1
        )
    )

    rank_merged = by_asset.merge(
        expected_ranked[
            [
                "asset",
                "timeframe",
                "metric_wins",
                "mean_metric_rank",
            ]
        ],
        on=[
            "asset",
            "timeframe",
        ],
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    checks[
        "asset_metric_wins_correct"
    ] = numeric_equal(
        rank_merged[
            "metric_wins_actual"
        ],
        rank_merged[
            "metric_wins_expected"
        ],
    )

    checks[
        "asset_mean_rank_correct"
    ] = numeric_equal(
        rank_merged[
            "mean_metric_rank_actual"
        ],
        rank_merged[
            "mean_metric_rank_expected"
        ],
    )

    return checks


def validate_15d(
    master,
    comparison_15d,
):
    checks = {}

    primary = master[
        master[
            "average_type"
        ]
        .astype(str)
        .str.lower()
        == "15d"
    ].copy()

    checks[
        "master_15d_has_27_rows"
    ] = (
        len(primary) == 27
    )

    expected = (
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

    checks[
        "15d_table_has_3_rows"
    ] = (
        len(
            comparison_15d
        )
        == 3
    )

    merged = comparison_15d.merge(
        expected,
        on="timeframe",
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    for column in (
        QUALITY_METRICS
        + [
            "event_count"
        ]
    ):

        checks[
            f"15d_{column}_correct"
        ] = numeric_equal(
            merged[
                f"{column}_actual"
            ],
            merged[
                f"{column}_expected"
            ],
        )

    expected_ranked = expected.copy()

    for metric in QUALITY_METRICS:

        expected_ranked[
            f"{metric}_rank"
        ] = (
            expected_ranked[
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

    expected_ranked[
        "metric_wins"
    ] = (
        expected_ranked[
            rank_columns
        ]
        .eq(1)
        .sum(
            axis=1
        )
    )

    expected_ranked[
        "mean_metric_rank"
    ] = (
        expected_ranked[
            rank_columns
        ]
        .mean(
            axis=1
        )
    )

    rank_merged = comparison_15d.merge(
        expected_ranked[
            [
                "timeframe",
                "metric_wins",
                "mean_metric_rank",
            ]
        ],
        on="timeframe",
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    checks[
        "15d_metric_wins_correct"
    ] = numeric_equal(
        rank_merged[
            "metric_wins_actual"
        ],
        rank_merged[
            "metric_wins_expected"
        ],
    )

    checks[
        "15d_mean_rank_correct"
    ] = numeric_equal(
        rank_merged[
            "mean_metric_rank_actual"
        ],
        rank_merged[
            "mean_metric_rank_expected"
        ],
    )

    return checks


def validate_spread(
    overall,
    spread,
):
    checks = {}

    checks[
        "spread_has_7_rows"
    ] = (
        len(
            spread
        )
        == len(
            QUALITY_METRICS
        )
    )

    expected_rows = []

    for metric in QUALITY_METRICS:

        values = (
            overall[
                metric
            ]
            .astype(float)
        )

        min_value = (
            values.min()
        )

        max_value = (
            values.max()
        )

        mean_value = (
            values.mean()
        )

        spread_value = (
            max_value
            - min_value
        )

        if mean_value != 0:

            relative_spread = (
                abs(
                    spread_value
                )
                / abs(
                    mean_value
                )
                * 100
            )

        else:

            relative_spread = None

        expected_rows.append(
            {
                "metric": metric,
                "min_value": min_value,
                "max_value": max_value,
                "spread": spread_value,
                "mean_value": mean_value,
                "relative_spread_pct": (
                    relative_spread
                ),
            }
        )

    expected = pd.DataFrame(
        expected_rows
    )

    merged = spread.merge(
        expected,
        on="metric",
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    for column in [
        "min_value",
        "max_value",
        "spread",
        "mean_value",
        "relative_spread_pct",
    ]:

        checks[
            f"spread_{column}_correct"
        ] = numeric_equal(
            merged[
                f"{column}_actual"
            ],
            merged[
                f"{column}_expected"
            ],
        )

    return checks


def main():

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    master = pd.read_csv(
        MASTER_FILE
    )

    overall = pd.read_csv(
        OVERALL_FILE
    )

    by_asset = pd.read_csv(
        ASSET_FILE
    )

    comparison_15d = pd.read_csv(
        PRIMARY_15D_FILE
    )

    spread = pd.read_csv(
        SPREAD_FILE
    )

    checks = {}

    checks.update(
        validate_overall(
            master,
            overall,
        )
    )

    checks.update(
        validate_by_asset(
            master,
            by_asset,
        )
    )

    checks.update(
        validate_15d(
            master,
            comparison_15d,
        )
    )

    checks.update(
        validate_spread(
            overall,
            spread,
        )
    )

    # ---------------------------------------------------------
    # Confirm event_count is NOT part of the quality metrics.
    # ---------------------------------------------------------

    checks[
        "event_count_not_ranked_as_quality"
    ] = (
        "event_count"
        not in QUALITY_METRICS
    )

    report = pd.DataFrame(
        [
            {
                "check": key,
                "pass": bool(value),
            }
            for key, value
            in checks.items()
        ]
    )

    output_file = (
        REPORT_DIR
        / "timeframe_comparison_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    failed = report[
        report[
            "pass"
        ]
        == False
    ]

    print(
        "\n"
        + "=" * 80
    )

    print(
        "TIMEFRAME COMPARISON VALIDATION"
    )

    print(
        "=" * 80
    )

    if len(
        failed
    ) == 0:

        print(
            "ALL CHECKS PASS"
        )

    else:

        print(
            "FAILED CHECKS:"
        )

        print(
            failed.to_string(
                index=False
            )
        )

    print(
        "\nChecks:",
        len(
            report
        ),
    )

    print(
        "Passed:",
        int(
            report[
                "pass"
            ].sum()
        ),
    )

    print(
        "Failed:",
        int(
            (
                ~report[
                    "pass"
                ]
            ).sum()
        ),
    )

    print(
        "\nReport saved:"
    )

    print(
        output_file
    )


if __name__ == "__main__":
    main()