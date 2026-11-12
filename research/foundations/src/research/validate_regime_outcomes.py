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
REPORT_DIR = Path("results/reports")

MASTER_FILE = (
    RESULTS_DIR
    / "regime_comparison_master.csv"
)

OVERALL_FILE = (
    RESULTS_DIR
    / "regime_overall_comparison.csv"
)

BY_ASSET_FILE = (
    RESULTS_DIR
    / "regime_comparison_by_asset.csv"
)

PRIMARY_FILE = (
    RESULTS_DIR
    / "regime_primary_setup_comparison.csv"
)


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


OVERALL_METRICS = [
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


def safe_pct(
    numerator,
    denominator,
):
    if denominator == 0:
        return np.nan

    return (
        numerator
        / denominator
        * 100
    )


def numeric_equal(
    actual,
    expected,
    rtol=1e-9,
    atol=1e-9,
):
    a = pd.to_numeric(
        actual,
        errors="coerce",
    ).to_numpy(
        dtype=float,
    )

    e = pd.to_numeric(
        expected,
        errors="coerce",
    ).to_numpy(
        dtype=float,
    )

    return bool(
        np.all(
            (
                np.isnan(a)
                & np.isnan(e)
            )
            |
            np.isclose(
                np.nan_to_num(a),
                np.nan_to_num(e),
                rtol=rtol,
                atol=atol,
            )
        )
    )


def load_full_event_data():
    frames = []

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

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

            outcomes = pd.read_parquet(
                outcome_file
            )

            regimes = pd.read_parquet(
                regime_file,
                columns=[
                    "event_id",
                    "market_regime",
                ],
            )

            if regimes[
                "event_id"
            ].duplicated().any():
                raise ValueError(
                    f"{symbol} {timeframe}: duplicate event_id"
                )

            original_rows = len(
                outcomes
            )

            merged = outcomes.merge(
                regimes,
                on="event_id",
                how="left",
                validate="one_to_one",
            )

            if len(
                merged
            ) != original_rows:
                raise ValueError(
                    f"{symbol} {timeframe}: row count changed"
                )

            merged = merged[
                merged[
                    "market_regime"
                ].notna()
            ].copy()

            frames.append(
                merged
            )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def summarize_group(
    group,
):
    result = {}

    # ---------------------------------------------------------
    # Event count
    # ---------------------------------------------------------

    result[
        "event_count"
    ] = len(
        group
    )

    # ---------------------------------------------------------
    # Forward returns
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # +2.5 reach
    # ---------------------------------------------------------

    reach = group[
        "reached_2_5_pct"
    ]

    valid_reach = (
        reach.notna()
    )

    reach_valid_count = int(
        valid_reach.sum()
    )

    reach_count = int(
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
    ] = reach_count

    result[
        "reach_2_5_probability_pct"
    ] = safe_pct(
        reach_count,
        reach_valid_count,
    )

    result[
        "median_time_to_2_5_minutes"
    ] = (
        group.loc[
            reach == True,
            "time_to_2_5_pct_minutes",
        ]
        .median()
    )

    # ---------------------------------------------------------
    # MAE
    # ---------------------------------------------------------

    mae_valid = (
        group[
            "downside_window_complete_24h"
        ]
        .fillna(False)
    )

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

    # ---------------------------------------------------------
    # MFE
    # ---------------------------------------------------------

    mfe_valid = (
        group[
            "upside_window_complete_24h"
        ]
        .fillna(False)
    )

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

    # ---------------------------------------------------------
    # First-hit
    # ---------------------------------------------------------

    outcome = (
        group[
            "target_2_5_vs_stop_2_5_outcome"
        ]
        .astype(
            "string"
        )
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

    # ---------------------------------------------------------
    # Post activation
    # ---------------------------------------------------------

    activated = (
        group[
            "trailing_activation_reached"
        ]
        .fillna(False)
    )

    result[
        "activated_2_5_count"
    ] = int(
        activated.sum()
    )

    post_valid = (
        activated
        &
        group[
            "post_activation_window_complete_24h"
        ]
        .fillna(False)
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

    # ---------------------------------------------------------
    # 30% trailing
    # ---------------------------------------------------------

    trail = (
        group[
            "trail_30_outcome"
        ]
        .astype(
            "string"
        )
    )

    resolved = (
        trail
        == "triggered_resolved"
    )

    ambiguous_trail = (
        trail
        == "ambiguous_same_candle"
    )

    no_trigger = (
        trail
        == "no_trigger"
    )

    incomplete_trail = (
        trail
        == "incomplete_unknown"
    )

    resolved_count = int(
        resolved.sum()
    )

    ambiguous_count = int(
        ambiguous_trail.sum()
    )

    no_trigger_count = int(
        no_trigger.sum()
    )

    incomplete_count = int(
        incomplete_trail.sum()
    )

    known = (
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
        known,
    )

    result[
        "trail30_ambiguous_pct"
    ] = safe_pct(
        ambiguous_count,
        known,
    )

    result[
        "trail30_no_trigger_pct"
    ] = safe_pct(
        no_trigger_count,
        known,
    )

    resolved_rows = group[
        resolved
    ]

    result[
        "trail30_median_locked_profit_pct"
    ] = (
        resolved_rows[
            "trail_30_old_locked_profit_pct"
        ]
        .median()
    )

    result[
        "trail30_mean_locked_profit_pct"
    ] = (
        resolved_rows[
            "trail_30_old_locked_profit_pct"
        ]
        .mean()
    )

    result[
        "trail30_median_time_minutes"
    ] = (
        resolved_rows[
            "trail_30_time_minutes"
        ]
        .median()
    )

    return result


def rebuild_master(
    data,
):
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

    return pd.DataFrame(
        rows
    )


def compare_master(
    actual,
    expected,
):
    checks = {}

    checks[
        "master_row_count_correct"
    ] = (
        len(actual)
        == len(expected)
    )

    merged = actual.merge(
        expected,
        on=GROUP_COLUMNS,
        suffixes=(
            "_actual",
            "_expected",
        ),
        validate="one_to_one",
    )

    metric_columns = [
        column
        for column
        in expected.columns
        if column
        not in GROUP_COLUMNS
    ]

    for column in metric_columns:

        checks[
            f"master_{column}_correct"
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

    print(
        "Loading event-level research data..."
    )

    data = load_full_event_data()

    print(
        f"Classified event rows: {len(data):,}"
    )

    actual_master = pd.read_csv(
        MASTER_FILE
    )

    actual_overall = pd.read_csv(
        OVERALL_FILE
    )

    actual_by_asset = pd.read_csv(
        BY_ASSET_FILE
    )

    actual_primary = pd.read_csv(
        PRIMARY_FILE
    )

    print(
        "Rebuilding regime master from event-level data..."
    )

    expected_master = rebuild_master(
        data
    )

    checks = {}

    # ---------------------------------------------------------
    # Full master
    # ---------------------------------------------------------

    checks.update(
        compare_master(
            actual_master,
            expected_master,
        )
    )

    # ---------------------------------------------------------
    # Expected 243 combinations
    # ---------------------------------------------------------

    checks[
        "master_has_243_rows"
    ] = (
        len(
            actual_master
        )
        == 243
    )

    checks[
        "all_three_regimes_present"
    ] = (
        set(
            actual_master[
                "market_regime"
            ]
        )
        == {
            "bullish",
            "neutral",
            "bearish",
        }
    )

    # ---------------------------------------------------------
    # Overall summary
    # ---------------------------------------------------------

    expected_overall = (
        expected_master
        .groupby(
            "market_regime"
        )[
            OVERALL_METRICS
        ]
        .median()
        .reset_index()
    )

    checks[
        "overall_has_3_rows"
    ] = (
        len(
            actual_overall
        )
        == 3
    )

    overall_merged = (
        actual_overall
        .merge(
            expected_overall,
            on="market_regime",
            suffixes=(
                "_actual",
                "_expected",
            ),
            validate="one_to_one",
        )
    )

    for column in OVERALL_METRICS:

        checks[
            f"overall_{column}_correct"
        ] = numeric_equal(
            overall_merged[
                f"{column}_actual"
            ],
            overall_merged[
                f"{column}_expected"
            ],
        )

    # ---------------------------------------------------------
    # Asset summary
    # ---------------------------------------------------------

    expected_by_asset = (
        expected_master
        .groupby(
            [
                "asset",
                "market_regime",
            ]
        )[
            OVERALL_METRICS
        ]
        .median()
        .reset_index()
    )

    checks[
        "by_asset_has_9_rows"
    ] = (
        len(
            actual_by_asset
        )
        == 9
    )

    asset_merged = (
        actual_by_asset
        .merge(
            expected_by_asset,
            on=[
                "asset",
                "market_regime",
            ],
            suffixes=(
                "_actual",
                "_expected",
            ),
            validate="one_to_one",
        )
    )

    for column in OVERALL_METRICS:

        checks[
            f"by_asset_{column}_correct"
        ] = numeric_equal(
            asset_merged[
                f"{column}_actual"
            ],
            asset_merged[
                f"{column}_expected"
            ],
        )

    # ---------------------------------------------------------
    # Primary setup
    # ---------------------------------------------------------

    expected_primary = expected_master[
        (
            expected_master[
                "asset"
            ]
            == "SOLUSDT"
        )
        &
        (
            expected_master[
                "timeframe"
            ]
            == "5m"
        )
        &
        (
            expected_master[
                "average_type"
            ]
            .astype(str)
            .str.lower()
            == "15d"
        )
        &
        (
            np.isclose(
                expected_master[
                    "touch_zone"
                ]
                .astype(float),
                0.5,
            )
        )
    ].copy()

    checks[
        "primary_has_3_rows"
    ] = (
        len(
            actual_primary
        )
        == 3
    )

    checks[
        "primary_regimes_correct"
    ] = (
        set(
            actual_primary[
                "market_regime"
            ]
        )
        == {
            "bullish",
            "neutral",
            "bearish",
        }
    )

    primary_merged = (
        actual_primary
        .merge(
            expected_primary,
            on=GROUP_COLUMNS,
            suffixes=(
                "_actual",
                "_expected",
            ),
            validate="one_to_one",
        )
    )

    metric_columns = [
        column
        for column
        in expected_primary.columns
        if column
        not in GROUP_COLUMNS
    ]

    for column in metric_columns:

        checks[
            f"primary_{column}_correct"
        ] = numeric_equal(
            primary_merged[
                f"{column}_actual"
            ],
            primary_merged[
                f"{column}_expected"
            ],
        )

    # ---------------------------------------------------------
    # Logical reconciliation checks
    # ---------------------------------------------------------

    checks[
        "reach_counts_do_not_exceed_valid"
    ] = bool(
        (
            actual_master[
                "reach_2_5_count"
            ]
            <= actual_master[
                "reach_2_5_valid_count"
            ]
        )
        .all()
    )

    checks[
        "first_hit_counts_reconcile"
    ] = bool(
        (
            actual_master[
                "first_hit_target_count"
            ]
            + actual_master[
                "first_hit_stop_count"
            ]
            + actual_master[
                "first_hit_ambiguous_count"
            ]
            + actual_master[
                "first_hit_neither_count"
            ]
            ==
            actual_master[
                "first_hit_confirmed_count"
            ]
        )
        .all()
    )

    checks[
        "trailing_known_percentages_sum_100"
    ] = bool(
        np.allclose(
            (
                actual_master[
                    "trail30_resolved_pct"
                ]
                + actual_master[
                    "trail30_ambiguous_pct"
                ]
                + actual_master[
                    "trail30_no_trigger_pct"
                ]
            )
            .dropna()
            .to_numpy(),
            100.0,
            atol=1e-8,
        )
    )

    checks[
        "post_activation_valid_not_above_activated"
    ] = bool(
        (
            actual_master[
                "post_activation_24h_valid_count"
            ]
            <= actual_master[
                "activated_2_5_count"
            ]
        )
        .all()
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

    report_file = (
        REPORT_DIR
        / "regime_outcome_validation.csv"
    )

    report.to_csv(
        report_file,
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
        "REGIME OUTCOME VALIDATION"
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
        "\nReport saved:"
    )

    print(
        report_file
    )


if __name__ == "__main__":
    main()