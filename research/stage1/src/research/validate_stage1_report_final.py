from pathlib import Path

import numpy as np
import pandas as pd


TABLES_DIR = Path("results/tables")
REPORTS_DIR = Path("results/reports")

SUMMARY_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary.csv"
)

PRE_FORWARD_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary_pre_forward_returns.csv"
)

FORWARD_FILE = (
    TABLES_DIR
    / "forward_return_statistics.csv"
)

AVERAGE_FILE = (
    TABLES_DIR
    / "average_overall_summary.csv"
)

TIMEFRAME_FILE = (
    TABLES_DIR
    / "timeframe_comparison_overall.csv"
)

ASSET_FILE = (
    TABLES_DIR
    / "asset_comparison_overall.csv"
)

REGIME_FILE = (
    TABLES_DIR
    / "regime_primary_setup_comparison.csv"
)

REPORT_FILE = (
    REPORTS_DIR
    / "stage1_research_report.md"
)

OUTPUT_FILE = (
    REPORTS_DIR
    / "stage1_report_final_validation.csv"
)


KEYS = [
    "asset",
    "timeframe",
    "average_type",
    "touch_zone",
]


HORIZONS = [
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "24h",
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
        dtype=float,
    )

    right = pd.to_numeric(
        right,
        errors="coerce",
    ).to_numpy(
        dtype=float,
    )

    # NaN locations must match exactly.
    left_nan = np.isnan(
        left
    )

    right_nan = np.isnan(
        right
    )

    if not np.array_equal(
        left_nan,
        right_nan,
    ):
        return False

    valid = ~left_nan

    if not valid.any():
        return True

    return bool(
        np.allclose(
            left[
                valid
            ],
            right[
                valid
            ],
            rtol=rtol,
            atol=atol,
        )
    )


def main():

    checks = {}

    # ---------------------------------------------------------
    # Required files
    # ---------------------------------------------------------

    required_files = {
        "summary_file_exists":
            SUMMARY_FILE,
        "pre_forward_backup_exists":
            PRE_FORWARD_FILE,
        "forward_statistics_exists":
            FORWARD_FILE,
        "average_summary_exists":
            AVERAGE_FILE,
        "timeframe_summary_exists":
            TIMEFRAME_FILE,
        "asset_summary_exists":
            ASSET_FILE,
        "regime_summary_exists":
            REGIME_FILE,
        "report_file_exists":
            REPORT_FILE,
    }

    for name, path in required_files.items():

        checks[
            name
        ] = path.exists()

    missing_files = [
        str(
            path
        )
        for path in required_files.values()
        if not path.exists()
    ]

    if missing_files:

        raise FileNotFoundError(
            "Missing required files:\n"
            + "\n".join(
                missing_files
            )
        )

    # ---------------------------------------------------------
    # Load data
    # ---------------------------------------------------------

    summary = pd.read_csv(
        SUMMARY_FILE
    )

    pre_forward = pd.read_csv(
        PRE_FORWARD_FILE
    )

    forward = pd.read_csv(
        FORWARD_FILE
    )

    average_summary = pd.read_csv(
        AVERAGE_FILE
    )

    timeframe_summary = pd.read_csv(
        TIMEFRAME_FILE
    )

    asset_summary = pd.read_csv(
        ASSET_FILE
    )

    regime = pd.read_csv(
        REGIME_FILE
    )

    report_text = REPORT_FILE.read_text(
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # Normalize key types
    # ---------------------------------------------------------

    for df in [
        summary,
        pre_forward,
        forward,
    ]:

        df[
            "average_type"
        ] = (
            df[
                "average_type"
            ]
            .astype(str)
        )

        df[
            "touch_zone"
        ] = (
            df[
                "touch_zone"
            ]
            .astype(float)
        )

    # ---------------------------------------------------------
    # Configuration integrity
    # ---------------------------------------------------------

    checks[
        "summary_has_81_rows"
    ] = (
        len(
            summary
        )
        == 81
    )

    checks[
        "pre_forward_has_81_rows"
    ] = (
        len(
            pre_forward
        )
        == 81
    )

    checks[
        "forward_has_81_rows"
    ] = (
        len(
            forward
        )
        == 81
    )

    checks[
        "summary_no_duplicate_configs"
    ] = (
        not summary[
            KEYS
        ]
        .duplicated()
        .any()
    )

    checks[
        "pre_forward_no_duplicate_configs"
    ] = (
        not pre_forward[
            KEYS
        ]
        .duplicated()
        .any()
    )

    checks[
        "forward_no_duplicate_configs"
    ] = (
        not forward[
            KEYS
        ]
        .duplicated()
        .any()
    )

    # ---------------------------------------------------------
    # Asset/config coverage
    # ---------------------------------------------------------

    checks[
        "summary_assets_correct"
    ] = (
        set(
            summary[
                "asset"
            ]
        )
        ==
        {
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
        }
    )

    checks[
        "summary_timeframes_correct"
    ] = (
        set(
            summary[
                "timeframe"
            ]
        )
        ==
        {
            "1m",
            "3m",
            "5m",
        }
    )

    checks[
        "summary_averages_correct"
    ] = (
        set(
            summary[
                "average_type"
            ]
            .astype(str)
        )
        ==
        {
            "7d",
            "15d",
            "30d",
        }
    )

    checks[
        "summary_zones_correct"
    ] = (
        set(
            summary[
                "touch_zone"
            ]
            .astype(float)
        )
        ==
        {
            0.5,
            1.0,
            1.5,
        }
    )

    asset_counts = (
        summary
        .groupby(
            "asset"
        )
        .size()
    )

    checks[
        "27_configurations_per_asset"
    ] = (
        len(
            asset_counts
        )
        == 3
        and
        asset_counts
        .eq(
            27
        )
        .all()
    )

    # ---------------------------------------------------------
    # Pre-forward summary must still match
    #
    # Adding forward metrics must not alter existing Stage 1
    # metrics.
    # ---------------------------------------------------------

    common_columns = [
        column
        for column in pre_forward.columns
        if column in summary.columns
    ]

    pre_sorted = (
        pre_forward[
            common_columns
        ]
        .sort_values(
            KEYS
        )
        .reset_index(
            drop=True
        )
    )

    summary_sorted = (
        summary[
            common_columns
        ]
        .sort_values(
            KEYS
        )
        .reset_index(
            drop=True
        )
    )

    unchanged = True

    for column in common_columns:

        if pd.api.types.is_numeric_dtype(
            pre_sorted[
                column
            ]
        ):

            same = numeric_equal(
                pre_sorted[
                    column
                ],
                summary_sorted[
                    column
                ],
            )

        else:

            same = (
                pre_sorted[
                    column
                ]
                .astype(str)
                .equals(
                    summary_sorted[
                        column
                    ]
                    .astype(str)
                )
            )

        if not same:

            unchanged = False
            break

    checks[
        "pre_forward_metrics_preserved"
    ] = unchanged

    # ---------------------------------------------------------
    # Forward-return columns
    # ---------------------------------------------------------

    forward_metric_columns = []

    for horizon in HORIZONS:

        forward_metric_columns += [
            f"return_{horizon}_valid_count",
            f"return_{horizon}_median_pct",
            f"return_{horizon}_mean_pct",
        ]

    checks[
        "all_18_forward_columns_present"
    ] = (
        all(
            column in summary.columns
            for column in forward_metric_columns
        )
    )

    checks[
        "forward_total_event_count_present"
    ] = (
        "forward_return_total_event_count"
        in summary.columns
    )

    if checks[
        "all_18_forward_columns_present"
    ]:

        checks[
            "no_missing_forward_values"
        ] = (
            not summary[
                forward_metric_columns
            ]
            .isna()
            .any()
            .any()
        )

    else:

        checks[
            "no_missing_forward_values"
        ] = False

    # ---------------------------------------------------------
    # Forward table must match merged summary
    # ---------------------------------------------------------

    forward_compare = forward.rename(
        columns={
            "event_count":
            "forward_return_total_event_count"
        }
    )

    comparison_columns = (
        KEYS
        + [
            "forward_return_total_event_count",
        ]
        + forward_metric_columns
    )

    forward_sorted = (
        forward_compare[
            comparison_columns
        ]
        .sort_values(
            KEYS
        )
        .reset_index(
            drop=True
        )
    )

    summary_forward_sorted = (
        summary[
            comparison_columns
        ]
        .sort_values(
            KEYS
        )
        .reset_index(
            drop=True
        )
    )

    forward_match = True

    for column in comparison_columns:

        if pd.api.types.is_numeric_dtype(
            forward_sorted[
                column
            ]
        ):

            same = numeric_equal(
                forward_sorted[
                    column
                ],
                summary_forward_sorted[
                    column
                ],
            )

        else:

            same = (
                forward_sorted[
                    column
                ]
                .astype(str)
                .equals(
                    summary_forward_sorted[
                        column
                    ]
                    .astype(str)
                )
            )

        if not same:

            forward_match = False
            break

    checks[
        "merged_forward_metrics_match_source"
    ] = forward_match

    # ---------------------------------------------------------
    # Event count relationships
    # ---------------------------------------------------------

    checks[
        "stage1_event_count_equals_24h_valid"
    ] = (
        (
            summary[
                "event_count"
            ]
            ==
            summary[
                "return_24h_valid_count"
            ]
        )
        .all()
    )

    checks[
        "forward_total_gte_24h_valid"
    ] = (
        (
            summary[
                "forward_return_total_event_count"
            ]
            >=
            summary[
                "return_24h_valid_count"
            ]
        )
        .all()
    )

    # ---------------------------------------------------------
    # Valid counts must be monotonic by horizon
    # ---------------------------------------------------------

    valid_count_columns = [
        f"return_{horizon}_valid_count"
        for horizon in HORIZONS
    ]

    for previous, current in zip(
        valid_count_columns,
        valid_count_columns[
            1:
        ],
    ):

        checks[
            f"{previous}_gte_{current}"
        ] = (
            (
                summary[
                    previous
                ]
                >=
                summary[
                    current
                ]
            )
            .all()
        )

    # ---------------------------------------------------------
    # Shorter-horizon counts cannot exceed total events
    # ---------------------------------------------------------

    for column in valid_count_columns:

        checks[
            f"{column}_lte_total_events"
        ] = (
            (
                summary[
                    column
                ]
                <=
                summary[
                    "forward_return_total_event_count"
                ]
            )
            .all()
        )

    # ---------------------------------------------------------
    # Primary setup
    # ---------------------------------------------------------

    primary = summary[
        (
            summary[
                "asset"
            ]
            == "SOLUSDT"
        )
        &
        (
            summary[
                "timeframe"
            ]
            == "5m"
        )
        &
        (
            summary[
                "average_type"
            ]
            == "15d"
        )
        &
        (
            np.isclose(
                summary[
                    "touch_zone"
                ],
                0.5,
            )
        )
    ]

    checks[
        "primary_setup_exists_exactly_once"
    ] = (
        len(
            primary
        )
        == 1
    )

    if len(
        primary
    ) == 1:

        primary = primary.iloc[
            0
        ]

        checks[
            "primary_forward_total_gte_complete"
        ] = (
            primary[
                "forward_return_total_event_count"
            ]
            >=
            primary[
                "event_count"
            ]
        )

        checks[
            "primary_reach_probability_valid"
        ] = (
            0
            <=
            primary[
                "reach_probability_pct"
            ]
            <=
            100
        )

        checks[
            "primary_mae_nonpositive"
        ] = (
            primary[
                "mae_24h_median_pct"
            ]
            <=
            0
        )

        checks[
            "primary_mfe_nonnegative"
        ] = (
            primary[
                "mfe_24h_median_pct"
            ]
            >=
            0
        )

    # ---------------------------------------------------------
    # Average conclusion
    # ---------------------------------------------------------

    best_average = (
        average_summary
        .sort_values(
            "mean_metric_rank"
        )
        .iloc[
            0
        ][
            "average_type"
        ]
    )

    checks[
        "15d_best_average_by_existing_rank"
    ] = (
        str(
            best_average
        )
        == "15d"
    )

    # ---------------------------------------------------------
    # Timeframe conclusion
    #
    # We do NOT require 5m to have the best rank.
    # The corrected conclusion is that the three are similar
    # and 5m is an operational candidate.
    # ---------------------------------------------------------

    checks[
        "three_timeframes_present"
    ] = (
        set(
            timeframe_summary[
                "timeframe"
            ]
        )
        ==
        {
            "1m",
            "3m",
            "5m",
        }
    )

    # ---------------------------------------------------------
    # Asset conclusion
    # ---------------------------------------------------------

    best_asset = (
        asset_summary
        .sort_values(
            "mean_metric_rank"
        )
        .iloc[
            0
        ][
            "asset"
        ]
    )

    checks[
        "SOL_best_opportunity_asset_by_existing_rank"
    ] = (
        best_asset
        == "SOLUSDT"
    )

    # BTC should have smaller median downside than SOL
    # in the overall asset summary.
    btc = asset_summary[
        asset_summary[
            "asset"
        ]
        == "BTCUSDT"
    ]

    sol = asset_summary[
        asset_summary[
            "asset"
        ]
        == "SOLUSDT"
    ]

    if (
        len(
            btc
        )
        == 1
        and
        len(
            sol
        )
        == 1
    ):

        btc = btc.iloc[
            0
        ]

        sol = sol.iloc[
            0
        ]

        checks[
            "BTC_has_smaller_downside_than_SOL"
        ] = (
            btc[
                "mae_24h_median_pct"
            ]
            >
            sol[
                "mae_24h_median_pct"
            ]
        )

    else:

        checks[
            "BTC_has_smaller_downside_than_SOL"
        ] = False

    # ---------------------------------------------------------
    # Regime integrity
    # ---------------------------------------------------------

    checks[
        "primary_regime_has_three_rows"
    ] = (
        len(
            regime
        )
        == 3
    )

    checks[
        "primary_regime_labels_correct"
    ] = (
        set(
            regime[
                "market_regime"
            ]
        )
        ==
        {
            "bullish",
            "neutral",
            "bearish",
        }
    )

    neutral = regime[
        regime[
            "market_regime"
        ]
        == "neutral"
    ]

    bearish = regime[
        regime[
            "market_regime"
        ]
        == "bearish"
    ]

    bullish = regime[
        regime[
            "market_regime"
        ]
        == "bullish"
    ]

    if (
        len(
            neutral
        )
        == 1
        and
        len(
            bearish
        )
        == 1
        and
        len(
            bullish
        )
        == 1
    ):

        neutral = neutral.iloc[
            0
        ]

        bearish = bearish.iloc[
            0
        ]

        bullish = bullish.iloc[
            0
        ]

        checks[
            "neutral_best_mfe_mae_ratio"
        ] = (
            neutral[
                "median_mfe_mae_ratio"
            ]
            >
            bearish[
                "median_mfe_mae_ratio"
            ]
            and
            neutral[
                "median_mfe_mae_ratio"
            ]
            >
            bullish[
                "median_mfe_mae_ratio"
            ]
        )

        checks[
            "neutral_best_target_first_decisive"
        ] = (
            neutral[
                "target_first_decisive_pct"
            ]
            >
            bearish[
                "target_first_decisive_pct"
            ]
            and
            neutral[
                "target_first_decisive_pct"
            ]
            >
            bullish[
                "target_first_decisive_pct"
            ]
        )

        checks[
            "neutral_best_post_activation_upside"
        ] = (
            neutral[
                "post_activation_median_extra_upside_24h_pct"
            ]
            >
            bearish[
                "post_activation_median_extra_upside_24h_pct"
            ]
            and
            neutral[
                "post_activation_median_extra_upside_24h_pct"
            ]
            >
            bullish[
                "post_activation_median_extra_upside_24h_pct"
            ]
        )

        checks[
            "bearish_highest_reach"
        ] = (
            bearish[
                "reach_2_5_probability_pct"
            ]
            >
            neutral[
                "reach_2_5_probability_pct"
            ]
            and
            bearish[
                "reach_2_5_probability_pct"
            ]
            >
            bullish[
                "reach_2_5_probability_pct"
            ]
        )

        checks[
            "bullish_lowest_mfe_mae_ratio"
        ] = (
            bullish[
                "median_mfe_mae_ratio"
            ]
            <
            neutral[
                "median_mfe_mae_ratio"
            ]
            and
            bullish[
                "median_mfe_mae_ratio"
            ]
            <
            bearish[
                "median_mfe_mae_ratio"
            ]
        )

    # ---------------------------------------------------------
    # Report structure
    # ---------------------------------------------------------

    required_sections = [
        "# V1 Stage 1 Research Report",
        "## 1. Research Objective",
        "## 2. Experiment Scope",
        "## 3. Metrics Evaluated",
        "## 4. Event Count Definitions",
        "## 5. Forward Returns",
        "## 6. Average Comparison",
        "## 7. Timeframe Comparison",
        "## 8. Asset Comparison",
        "## 9. Touch-Zone Comparison",
        "## 10. Current Leading Research Configuration",
        "## 11. Market-Regime Findings",
        "## 12. +2.5% Activation and Trailing Research",
        "## 13. Interpretation of the Asset Ranking",
        "## 14. Important Limitations",
        "## 15. Stage 2 Research Candidates",
        "## 16. Final Stage 1 Conclusion",
    ]

    for section in required_sections:

        checks[
            f"report_section_present_{section}"
        ] = (
            section
            in report_text
        )

    # ---------------------------------------------------------
    # All forward horizons must appear in report
    # ---------------------------------------------------------

    forward_phrases = [
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
        "24h",
    ]

    for horizon in forward_phrases:

        checks[
            f"report_mentions_forward_horizon_{horizon}"
        ] = (
            horizon
            in report_text
        )

    checks[
        "report_mentions_forward_total_event_count"
    ] = (
        "forward_return_total_event_count"
        in report_text
    )

    checks[
        "report_mentions_24h_valid_definition"
    ] = (
        "return_24h_valid_count"
        in report_text
    )

    # ---------------------------------------------------------
    # Corrected conclusion language
    # ---------------------------------------------------------

    required_conclusion_phrases = [
        (
            "SOLUSDT is the strongest opportunity "
            "candidate"
        ),
        (
            "SOLUSDT is not universally the safest "
            "or best asset"
        ),
        (
            "15D remains the strongest supported "
            "primary average"
        ),
        (
            "1m, 3m and 5m behave very similarly"
        ),
        (
            "does not justify claiming that 5m is "
            "statistically superior"
        ),
        (
            "±0.5% remains the leading touch-zone "
            "candidate"
        ),
        (
            "Neutral"
        ),
        (
            "Bearish"
        ),
        (
            "30% giveback"
        ),
    ]

    for phrase in required_conclusion_phrases:

        checks[
            f"report_contains_{phrase}"
        ] = (
            phrase.lower()
            in report_text.lower()
        )

    # ---------------------------------------------------------
    # Report must NOT make old overstatement
    # ---------------------------------------------------------

    prohibited_phrases = [
        "SOLUSDT is the best asset",
        "5m is the best timeframe",
        "0.5% is the final touch zone",
        "finished trading strategy",
    ]

    for phrase in prohibited_phrases:

        checks[
            f"report_avoids_{phrase}"
        ] = (
            phrase.lower()
            not in report_text.lower()
        )

    # ---------------------------------------------------------
    # Limitations
    # ---------------------------------------------------------

    limitation_phrases = [
        "not independent trades",
        "nested",
        "overlapping",
        "correlated",
        "same-candle",
        "signal deduplication",
        "fees",
        "slippage",
        "out-of-sample",
    ]

    for phrase in limitation_phrases:

        checks[
            f"report_limitation_present_{phrase}"
        ] = (
            phrase.lower()
            in report_text.lower()
        )

    # ---------------------------------------------------------
    # Final report
    # ---------------------------------------------------------

    validation = pd.DataFrame(
        [
            {
                "check":
                    name,
                "pass":
                    bool(
                        result
                    ),
            }
            for name, result
            in checks.items()
        ]
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    validation.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    failed = validation[
        validation[
            "pass"
        ]
        == False
    ]

    print(
        "\n"
        + "=" * 100
    )

    print(
        "FINAL STAGE 1 REPORT VALIDATION"
    )

    print(
        "=" * 100
    )

    if len(
        failed
    ) == 0:

        print(
            "\nALL CHECKS PASS"
        )

    else:

        print(
            "\nFAILED CHECKS:"
        )

        print(
            failed.to_string(
                index=False
            )
        )

    print(
        "\nChecks:",
        len(
            validation
        ),
    )

    print(
        "Passed:",
        int(
            validation[
                "pass"
            ]
            .sum()
        ),
    )

    print(
        "Failed:",
        int(
            (
                ~validation[
                    "pass"
                ]
            )
            .sum()
        ),
    )

    print(
        "\nConfiguration rows:",
        len(
            summary
        ),
    )

    print(
        "Stage 1 summary columns:",
        len(
            summary.columns
        ),
    )

    print(
        "Forward-return metric columns:",
        len(
            forward_metric_columns
        ),
    )

    print(
        "\nValidation report:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()