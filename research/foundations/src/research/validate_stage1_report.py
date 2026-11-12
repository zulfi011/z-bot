from pathlib import Path

import numpy as np
import pandas as pd


TABLES_DIR = Path("results/tables")
REPORTS_DIR = Path("results/reports")

REPORT_FILE = (
    REPORTS_DIR
    / "stage1_research_report.md"
)

CONFIG_SUMMARY_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary.csv"
)

MASTER_FILE = (
    TABLES_DIR
    / "average_comparison_master.csv"
)

EXPERIMENT_GRID_FILE = (
    TABLES_DIR
    / "experiment_grid.csv"
)

AVERAGE_SUMMARY_FILE = (
    TABLES_DIR
    / "average_overall_summary.csv"
)

TIMEFRAME_SUMMARY_FILE = (
    TABLES_DIR
    / "timeframe_comparison_overall.csv"
)

ASSET_SUMMARY_FILE = (
    TABLES_DIR
    / "asset_comparison_overall.csv"
)

REGIME_PRIMARY_FILE = (
    TABLES_DIR
    / "regime_primary_setup_comparison.csv"
)

VALIDATION_OUTPUT = (
    REPORTS_DIR
    / "stage1_report_validation.csv"
)


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


def main():

    checks = {}

    # ---------------------------------------------------------
    # Files exist
    # ---------------------------------------------------------

    checks[
        "report_file_exists"
    ] = REPORT_FILE.exists()

    checks[
        "configuration_summary_exists"
    ] = CONFIG_SUMMARY_FILE.exists()

    if not REPORT_FILE.exists():
        raise FileNotFoundError(
            REPORT_FILE
        )

    if not CONFIG_SUMMARY_FILE.exists():
        raise FileNotFoundError(
            CONFIG_SUMMARY_FILE
        )

    # ---------------------------------------------------------
    # Load sources
    # ---------------------------------------------------------

    report_text = REPORT_FILE.read_text(
        encoding="utf-8",
    )

    config_summary = pd.read_csv(
        CONFIG_SUMMARY_FILE
    )

    master = pd.read_csv(
        MASTER_FILE
    )

    experiment_grid = pd.read_csv(
        EXPERIMENT_GRID_FILE
    )

    average_summary = pd.read_csv(
        AVERAGE_SUMMARY_FILE
    )

    timeframe_summary = pd.read_csv(
        TIMEFRAME_SUMMARY_FILE
    )

    asset_summary = pd.read_csv(
        ASSET_SUMMARY_FILE
    )

    regime_primary = pd.read_csv(
        REGIME_PRIMARY_FILE
    )

    # ---------------------------------------------------------
    # 81-row configuration summary must equal master
    # ---------------------------------------------------------

    checks[
        "configuration_summary_has_81_rows"
    ] = (
        len(config_summary)
        == 81
    )

    checks[
        "master_has_81_rows"
    ] = (
        len(master)
        == 81
    )

    checks[
        "experiment_grid_has_81_rows"
    ] = (
        len(experiment_grid)
        == 81
    )

    setup_columns = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    config_sorted = (
        config_summary
        .sort_values(
            setup_columns
        )
        .reset_index(
            drop=True
        )
    )

    master_sorted = (
        master
        .sort_values(
            setup_columns
        )
        .reset_index(
            drop=True
        )
    )

    checks[
        "configuration_summary_columns_match_master"
    ] = (
        list(
            config_sorted.columns
        )
        == list(
            master_sorted.columns
        )
    )

    if (
        checks[
            "configuration_summary_columns_match_master"
        ]
    ):

        all_columns_match = True

        for column in master_sorted.columns:

            if (
                pd.api.types.is_numeric_dtype(
                    master_sorted[
                        column
                    ]
                )
            ):

                same = numeric_equal(
                    config_sorted[
                        column
                    ],
                    master_sorted[
                        column
                    ],
                )

            else:

                same = (
                    config_sorted[
                        column
                    ]
                    .astype(str)
                    .equals(
                        master_sorted[
                            column
                        ]
                        .astype(str)
                    )
                )

            if not same:
                all_columns_match = False
                break

        checks[
            "configuration_summary_matches_master"
        ] = all_columns_match

    else:

        checks[
            "configuration_summary_matches_master"
        ] = False

    # ---------------------------------------------------------
    # Config combinations match experiment grid
    # ---------------------------------------------------------

    grid_setups = (
        experiment_grid[
            setup_columns
        ]
        .copy()
    )

    summary_setups = (
        config_summary[
            setup_columns
        ]
        .copy()
    )

    grid_setups[
        "average_type"
    ] = (
        grid_setups[
            "average_type"
        ]
        .astype(str)
    )

    summary_setups[
        "average_type"
    ] = (
        summary_setups[
            "average_type"
        ]
        .astype(str)
    )

    grid_setups[
        "touch_zone"
    ] = (
        grid_setups[
            "touch_zone"
        ]
        .astype(float)
    )

    summary_setups[
        "touch_zone"
    ] = (
        summary_setups[
            "touch_zone"
        ]
        .astype(float)
    )

    grid_setups = (
        grid_setups
        .sort_values(
            setup_columns
        )
        .reset_index(
            drop=True
        )
    )

    summary_setups = (
        summary_setups
        .sort_values(
            setup_columns
        )
        .reset_index(
            drop=True
        )
    )

    checks[
        "configuration_summary_matches_experiment_grid"
    ] = (
        grid_setups.equals(
            summary_setups
        )
    )

    # ---------------------------------------------------------
    # Report structure
    # ---------------------------------------------------------

    required_sections = [
        "# V1 Stage 1 Research Report",
        "## 1. Research Objective",
        "## 2. Experiment Scope",
        "## 3. Metrics Evaluated",
        "## 4. Average Comparison",
        "## 5. Timeframe Comparison",
        "## 6. Asset Comparison",
        "## 7. Leading Stage 1 Setup",
        "## 8. Market Regime Findings",
        "## 9. +2.5% Activation and Trailing Research",
        "## 10. Stage 2 Candidates",
        "## 11. Important Limitations",
        "## 12. Stage 1 Conclusion",
    ]

    for section in required_sections:

        checks[
            f"section_present_{section}"
        ] = (
            section
            in report_text
        )

    # ---------------------------------------------------------
    # Scope claims
    # ---------------------------------------------------------

    checks[
        "report_mentions_BTC"
    ] = (
        "BTCUSDT"
        in report_text
    )

    checks[
        "report_mentions_ETH"
    ] = (
        "ETHUSDT"
        in report_text
    )

    checks[
        "report_mentions_SOL"
    ] = (
        "SOLUSDT"
        in report_text
    )

    checks[
        "report_mentions_81_configurations"
    ] = (
        "Total configurations: 81"
        in report_text
    )

    checks[
        "report_mentions_27_per_asset"
    ] = (
        "Configurations per asset: 27"
        in report_text
    )

    # ---------------------------------------------------------
    # Average conclusion must agree with source table
    # ---------------------------------------------------------

    best_average = (
        average_summary
        .sort_values(
            "mean_metric_rank"
        )
        .iloc[0]
        [
            "average_type"
        ]
    )

    checks[
        "best_average_is_15d"
    ] = (
        str(
            best_average
        ).lower()
        == "15d"
    )

    checks[
        "report_identifies_15d_as_primary_average"
    ] = (
        "Primary average: 15D"
        in report_text
    )

    # ---------------------------------------------------------
    # Timeframe conclusion
    # ---------------------------------------------------------

    timeframe_values = set(
        timeframe_summary[
            "timeframe"
        ]
    )

    checks[
        "all_timeframes_present_in_source"
    ] = (
        timeframe_values
        == {
            "1m",
            "3m",
            "5m",
        }
    )

    checks[
        "report_identifies_5m_as_primary_timeframe"
    ] = (
        "Primary execution timeframe: 5m"
        in report_text
    )

    # ---------------------------------------------------------
    # Asset conclusion
    # ---------------------------------------------------------

    best_asset = (
        asset_summary
        .sort_values(
            "mean_metric_rank"
        )
        .iloc[0]
        [
            "asset"
        ]
    )

    checks[
        "best_asset_is_SOL"
    ] = (
        best_asset
        == "SOLUSDT"
    )

    checks[
        "report_identifies_SOL_as_primary_asset"
    ] = (
        "Primary asset candidate: SOLUSDT"
        in report_text
    )

    # ---------------------------------------------------------
    # Primary setup must exist exactly once
    # ---------------------------------------------------------

    primary = master[
        (
            master[
                "asset"
            ]
            == "SOLUSDT"
        )
        &
        (
            master[
                "timeframe"
            ]
            == "5m"
        )
        &
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
            np.isclose(
                master[
                    "touch_zone"
                ]
                .astype(float),
                0.5,
            )
        )
    ]

    checks[
        "primary_setup_exists_once"
    ] = (
        len(primary)
        == 1
    )

    checks[
        "report_primary_setup_mentions_SOL"
    ] = (
        "- Asset: SOLUSDT"
        in report_text
    )

    checks[
        "report_primary_setup_mentions_15D"
    ] = (
        "- Average: 15D"
        in report_text
    )

    checks[
        "report_primary_setup_mentions_5m"
    ] = (
        "- Timeframe: 5m"
        in report_text
    )

    checks[
        "report_primary_setup_mentions_0_5_zone"
    ] = (
        "- Touch zone: ±0.5%"
        in report_text
    )

    # ---------------------------------------------------------
    # Regime conclusion
    #
    # We validate from the primary regime table using the
    # balanced metrics that supported the conclusion.
    # ---------------------------------------------------------

    neutral = regime_primary[
        regime_primary[
            "market_regime"
        ]
        == "neutral"
    ]

    bearish = regime_primary[
        regime_primary[
            "market_regime"
        ]
        == "bearish"
    ]

    bullish = regime_primary[
        regime_primary[
            "market_regime"
        ]
        == "bullish"
    ]

    checks[
        "primary_has_three_regimes"
    ] = (
        len(neutral)
        == 1
        and len(bearish)
        == 1
        and len(bullish)
        == 1
    )

    if checks[
        "primary_has_three_regimes"
    ]:

        neutral = neutral.iloc[0]
        bearish = bearish.iloc[0]
        bullish = bullish.iloc[0]

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
            "bearish_highest_reach_probability"
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
    # Report conclusion language present
    # ---------------------------------------------------------

    checks[
        "report_identifies_neutral_as_preferred_regime"
    ] = (
        "Preferred regime candidate: Neutral"
        in report_text
    )

    checks[
        "report_identifies_bearish_as_higher_risk"
    ] = (
        "Higher-risk rebound regime: Bearish"
        in report_text
    )

    checks[
        "report_identifies_2_5_activation"
    ] = (
        "Activation candidate: +2.5%"
        in report_text
    )

    checks[
        "report_identifies_30pct_trailing"
    ] = (
        "Trailing candidate: 30% profit giveback"
        in report_text
    )

    # ---------------------------------------------------------
    # Important limitations present
    # ---------------------------------------------------------

    limitation_phrases = [
        "Touch events overlap",
        "Consecutive candles",
        "Wider touch zones are nested",
        "same-candle ambiguity",
        "fees, slippage",
        "not yet a live trading strategy",
    ]

    for phrase in limitation_phrases:

        checks[
            f"limitation_present_{phrase}"
        ] = (
            phrase.lower()
            in report_text.lower()
        )

    # ---------------------------------------------------------
    # Save validation report
    # ---------------------------------------------------------

    report = pd.DataFrame(
        [
            {
                "check": name,
                "pass": bool(
                    passed
                ),
            }
            for name, passed
            in checks.items()
        ]
    )

    VALIDATION_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report.to_csv(
        VALIDATION_OUTPUT,
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
        + "=" * 90
    )

    print(
        "STAGE 1 REPORT VALIDATION"
    )

    print(
        "=" * 90
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
        "\nValidation report:"
    )

    print(
        VALIDATION_OUTPUT
    )


if __name__ == "__main__":
    main()