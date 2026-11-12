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
    / "asset_comparison_overall.csv"
)

ASSET_15D_FILE = (
    RESULTS_DIR
    / "asset_comparison_15d.csv"
)

ASSET_15D_5M_FILE = (
    RESULTS_DIR
    / "asset_comparison_15d_5m.csv"
)

CONSISTENCY_FILE = (
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


def add_expected_ranks(
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


def validate_summary(
    source_df: pd.DataFrame,
    actual_df: pd.DataFrame,
    label: str,
):
    checks = {}

    expected = (
        source_df
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

    expected = add_expected_ranks(
        expected
    )

    checks[
        f"{label}_has_3_rows"
    ] = (
        len(actual_df)
        == 3
    )

    checks[
        f"{label}_assets_correct"
    ] = (
        set(
            actual_df[
                "asset"
            ]
        )
        == {
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
        }
    )

    merged = actual_df.merge(
        expected,
        on="asset",
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    for column in (
        QUALITY_METRICS
        + [
            "event_count",
            "metric_wins",
            "mean_metric_rank",
        ]
    ):

        checks[
            f"{label}_{column}_correct"
        ] = numeric_equal(
            merged[
                f"{column}_actual"
            ],
            merged[
                f"{column}_expected"
            ],
        )

    return checks


def validate_consistency(
    master: pd.DataFrame,
    actual: pd.DataFrame,
):
    checks = {}

    expected_rows = []

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

            expected_rows.append(
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

    expected = pd.DataFrame(
        expected_rows
    )

    checks[
        "consistency_row_count_correct"
    ] = (
        len(actual)
        == len(expected)
    )

    merged = actual.merge(
        expected,
        on=[
            "asset",
            "metric",
        ],
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    for column in [
        "mean_value",
        "median_value",
        "min_value",
        "max_value",
        "spread",
        "relative_spread_pct",
    ]:

        checks[
            f"consistency_{column}_correct"
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

    comparison_15d = pd.read_csv(
        ASSET_15D_FILE
    )

    comparison_15d_5m = pd.read_csv(
        ASSET_15D_5M_FILE
    )

    consistency = pd.read_csv(
        CONSISTENCY_FILE
    )

    checks = {}

    # ---------------------------------------------------------
    # Overall
    # ---------------------------------------------------------

    checks.update(
        validate_summary(
            master,
            overall,
            "overall",
        )
    )

    # ---------------------------------------------------------
    # 15D-only
    # ---------------------------------------------------------

    source_15d = master[
        master[
            "average_type"
        ]
        .astype(str)
        .str.lower()
        == "15d"
    ].copy()

    checks[
        "master_15d_row_count_27"
    ] = (
        len(source_15d)
        == 27
    )

    checks.update(
        validate_summary(
            source_15d,
            comparison_15d,
            "15d",
        )
    )

    # ---------------------------------------------------------
    # 15D + 5m
    # ---------------------------------------------------------

    source_15d_5m = master[
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

    checks[
        "master_15d_5m_row_count_9"
    ] = (
        len(source_15d_5m)
        == 9
    )

    checks.update(
        validate_summary(
            source_15d_5m,
            comparison_15d_5m,
            "15d_5m",
        )
    )

    # ---------------------------------------------------------
    # Consistency
    # ---------------------------------------------------------

    checks.update(
        validate_consistency(
            master,
            consistency,
        )
    )

    # ---------------------------------------------------------
    # Event count is context only, not quality ranking
    # ---------------------------------------------------------

    checks[
        "event_count_not_quality_metric"
    ] = (
        "event_count"
        not in QUALITY_METRICS
    )

    # ---------------------------------------------------------
    # Final report
    # ---------------------------------------------------------

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
        / "asset_comparison_validation.csv"
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
        "ASSET COMPARISON VALIDATION"
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