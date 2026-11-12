from pathlib import Path

import numpy as np
import pandas as pd


RESULTS_DIR = Path("results/tables")
REPORT_DIR = Path("results/reports")

MASTER_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)

SOURCE_FILES = {
    "profit_reach": RESULTS_DIR / "profit_reach_statistics.csv",
    "downside": RESULTS_DIR / "downside_statistics.csv",
    "upside": RESULTS_DIR / "upside_statistics.csv",
    "mfe_mae": RESULTS_DIR / "max_upside_downside_comparison.csv",
    "first_hit": RESULTS_DIR / "first_hit_statistics.csv",
    "post_activation": RESULTS_DIR / "post_activation_statistics.csv",
    "trailing": RESULTS_DIR / "trailing_outcome_comparison.csv",
}

KEYS = [
    "asset",
    "timeframe",
    "average_type",
    "touch_zone",
]


def normalize_average_type(series):
    return (
        series.astype(str)
        .str.lower()
        .str.strip()
    )


def normalize_touch_zone(series):
    return pd.to_numeric(
        series,
        errors="coerce",
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
        dtype=np.float64
    )

    right = pd.to_numeric(
        right,
        errors="coerce",
    ).to_numpy(
        dtype=np.float64
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


def normalize_keys(df):
    df = df.copy()

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    return df


def validate_master_structure(master):
    checks = {}

    checks["row_count_81"] = (
        len(master) == 81
    )

    checks["unique_setup_keys"] = (
        master[
            KEYS
        ].duplicated().sum()
        == 0
    )

    checks["no_missing_values"] = (
        master.isna().sum().sum()
        == 0
    )

    checks["assets_correct"] = (
        set(master["asset"])
        == {
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
        }
    )

    checks["timeframes_correct"] = (
        set(master["timeframe"])
        == {
            "1m",
            "3m",
            "5m",
        }
    )

    checks["averages_correct"] = (
        set(master["average_type"])
        == {
            "7d",
            "15d",
            "30d",
        }
    )

    checks["zones_correct"] = (
        set(
            pd.to_numeric(
                master["touch_zone"]
            )
        )
        == {
            0.5,
            1.0,
            1.5,
        }
    )

    counts = (
        master
        .groupby(
            "average_type"
        )
        .size()
    )

    checks["27_rows_per_average"] = (
        counts.to_dict()
        == {
            "7d": 27,
            "15d": 27,
            "30d": 27,
        }
    )

    return checks

def compare_metric(
    master,
    source,
    source_column,
    master_column,
):
    master_part = master[
        KEYS
        + [
            master_column
        ]
    ].copy()

    source_part = source[
        KEYS
        + [
            source_column
        ]
    ].copy()

    master_value_column = (
        "__master_value"
    )

    source_value_column = (
        "__source_value"
    )

    master_part = master_part.rename(
        columns={
            master_column:
                master_value_column
        }
    )

    source_part = source_part.rename(
        columns={
            source_column:
                source_value_column
        }
    )

    merged = master_part.merge(
        source_part,
        on=KEYS,
        how="left",
        validate="one_to_one",
    )

    return numeric_equal(
        merged[
            master_value_column
        ],
        merged[
            source_value_column
        ],
    )

def main():

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Loading master table..."
    )

    master = pd.read_csv(
        MASTER_FILE
    )

    master = normalize_keys(
        master
    )

    checks = validate_master_structure(
        master
    )

    # ---------------------------------------------------------
    # Profit reach +2.5%
    # ---------------------------------------------------------

    profit = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "profit_reach"
            ]
        )
    )

    target_column = None

    for column in [
        "profit_level_pct",
        "target_pct",
        "profit_level",
    ]:
        if column in profit.columns:
            target_column = column
            break

    if target_column is None:
        raise ValueError(
            "Cannot find target column "
            "in profit_reach_statistics.csv"
        )

    targets = pd.to_numeric(
        profit[
            target_column
        ],
        errors="coerce",
    )

    if targets.max() <= 1:
        targets = (
            targets * 100
        )

    profit = profit[
        targets.round(6)
        == 2.5
    ].copy()

    event_source = None

    for column in [
        "valid_event_count",
        "valid_count",
        "event_count",
        "events",
    ]:
        if column in profit.columns:
            event_source = column
            break

    reach_source = None

    for column in [
        "reach_probability_pct",
        "probability_pct",
        "reached_pct",
        "reach_pct",
    ]:
        if column in profit.columns:
            reach_source = column
            break

    time_source = None

    for column in [
        "median_time_minutes",
        "median_time_to_reach_minutes",
        "median_time_to_target_minutes",
    ]:
        if column in profit.columns:
            time_source = column
            break

    checks[
        "profit_reach_has_81_rows"
    ] = (
        len(profit) == 81
    )

    if event_source:
        checks[
            "event_count_matches_source"
        ] = compare_metric(
            master,
            profit,
            event_source,
            "event_count",
        )

    if reach_source:
        checks[
            "reach_probability_matches_source"
        ] = compare_metric(
            master,
            profit,
            reach_source,
            "reach_probability_pct",
        )

    if (
        time_source
        and "median_time_to_target_minutes"
        in master.columns
    ):
        checks[
            "target_time_matches_source"
        ] = compare_metric(
            master,
            profit,
            time_source,
            "median_time_to_target_minutes",
        )

    # ---------------------------------------------------------
    # Downside 24h
    # ---------------------------------------------------------

    downside = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "downside"
            ]
        )
    )

    downside = downside[
        downside["window"].astype(str)
        == "24h"
    ].copy()

    checks[
        "downside_has_81_rows"
    ] = (
        len(downside) == 81
    )

    downside_map = {
        "median_downside_pct":
            "mae_24h_median_pct",
        "p90_severe_downside_pct":
            "mae_24h_severe10_pct",
        "p95_severe_downside_pct":
            "mae_24h_severe5_pct",
        "worst_downside_pct":
            "mae_24h_worst_pct",
    }

    for source_col, master_col in downside_map.items():
        checks[
            f"{master_col}_matches_source"
        ] = compare_metric(
            master,
            downside,
            source_col,
            master_col,
        )

    # ---------------------------------------------------------
    # Upside 24h
    # ---------------------------------------------------------

    upside = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "upside"
            ]
        )
    )

    upside = upside[
        upside["window"].astype(str)
        == "24h"
    ].copy()

    checks[
        "upside_has_81_rows"
    ] = (
        len(upside) == 81
    )

    upside_map = {
        "median_upside_pct":
            "mfe_24h_median_pct",
        "p75_upside_pct":
            "mfe_24h_p75_pct",
        "p90_upside_pct":
            "mfe_24h_p90_pct",
        "p95_upside_pct":
            "mfe_24h_p95_pct",
        "best_upside_pct":
            "mfe_24h_best_pct",
    }

    for source_col, master_col in upside_map.items():
        checks[
            f"{master_col}_matches_source"
        ] = compare_metric(
            master,
            upside,
            source_col,
            master_col,
        )

    # ---------------------------------------------------------
    # MFE / MAE comparison
    # ---------------------------------------------------------

    balance = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "mfe_mae"
            ]
        )
    )

    checks[
        "mfe_mae_has_81_rows"
    ] = (
        len(balance) == 81
    )

    if (
        "median_upside_to_downside_ratio"
        in balance.columns
    ):
        checks[
            "median_mfe_mae_ratio_matches_source"
        ] = compare_metric(
            master,
            balance,
            "median_upside_to_downside_ratio",
            "median_mfe_mae_ratio",
        )

    if (
        "median_excursion_balance"
        in balance.columns
    ):
        checks[
            "median_excursion_balance_matches_source"
        ] = compare_metric(
            master,
            balance,
            "median_excursion_balance",
            "median_excursion_balance_pct",
        )

    # ---------------------------------------------------------
    # First-hit target +2.5 vs stops
    # ---------------------------------------------------------

    first_hit = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "first_hit"
            ]
        )
    )

    for stop in [
        2.0,
        2.5,
        3.0,
    ]:

        subset = first_hit[
            pd.to_numeric(
                first_hit[
                    "stop_pct"
                ],
                errors="coerce",
            ).round(6)
            == stop
        ].copy()

        checks[
            f"first_hit_stop_{stop}_has_81_rows"
        ] = (
            len(subset) == 81
        )

        master_col = (
            f"target_2_5_first_vs_stop_"
            f"{str(stop).replace('.', '_')}_pct"
        )

        checks[
            f"{master_col}_matches_source"
        ] = compare_metric(
            master,
            subset,
            "target_first_pct_all_confirmed",
            master_col,
        )

    # ---------------------------------------------------------
    # Post-activation 24h
    # ---------------------------------------------------------

    post = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "post_activation"
            ]
        )
    )

    post = post[
        post["window"].astype(str)
        == "24h"
    ].copy()

    checks[
        "post_activation_has_81_rows"
    ] = (
        len(post) == 81
    )

    post_map = {
        "activated_event_rows":
            "post_activation_event_count",
        "median_extra_upside_pct":
            "post_activation_median_extra_upside_24h_pct",
        "p75_extra_upside_pct":
            "post_activation_p75_extra_upside_24h_pct",
        "p90_extra_upside_pct":
            "post_activation_p90_extra_upside_24h_pct",
        "median_time_to_peak_minutes":
            "post_activation_median_time_to_peak_24h_minutes",
        "median_retracement_pct":
            "post_activation_median_retracement_24h_pct",
        "p90_severe_retracement_pct":
            "post_activation_severe10_retracement_24h_pct",
    }

    for source_col, master_col in post_map.items():
        if master_col in master.columns:
            checks[
                f"{master_col}_matches_source"
            ] = compare_metric(
                master,
                post,
                source_col,
                master_col,
            )

    # ---------------------------------------------------------
    # Trailing 30%
    # ---------------------------------------------------------

    trailing = normalize_keys(
        pd.read_csv(
            SOURCE_FILES[
                "trailing"
            ]
        )
    )

    trailing = trailing[
        pd.to_numeric(
            trailing[
                "trail_giveback_pct"
            ],
            errors="coerce",
        ).round(6)
        == 30.0
    ].copy()

    checks[
        "trailing30_has_81_rows"
    ] = (
        len(trailing) == 81
    )

    trail_map = {
        "resolved_pct_confirmed":
            "trail30_resolved_pct",
        "ambiguous_pct_confirmed":
            "trail30_ambiguous_pct",
        "not_triggered_pct_confirmed":
            "trail30_not_triggered_24h_pct",
        "median_realized_return_pct":
            "trail30_median_realized_return_pct",
        "mean_realized_return_pct":
            "trail30_mean_realized_return_pct",
        "median_time_to_exit_minutes":
            "trail30_median_time_to_exit_minutes",
    }

    for source_col, master_col in trail_map.items():
        if master_col in master.columns:
            checks[
                f"{master_col}_matches_source"
            ] = compare_metric(
                master,
                trailing,
                source_col,
                master_col,
            )

    # ---------------------------------------------------------
    # Logical sanity checks
    # ---------------------------------------------------------

    checks[
        "event_counts_positive"
    ] = bool(
        (
            master[
                "event_count"
            ]
            > 0
        ).all()
    )

    checks[
        "reach_probabilities_valid"
    ] = bool(
        master[
            "reach_probability_pct"
        ].between(
            0,
            100,
        ).all()
    )

    checks[
        "mae_median_nonpositive"
    ] = bool(
        (
            master[
                "mae_24h_median_pct"
            ]
            <= 0
        ).all()
    )

    checks[
        "mfe_median_nonnegative"
    ] = bool(
        (
            master[
                "mfe_24h_median_pct"
            ]
            >= 0
        ).all()
    )

    checks[
        "mfe_mae_ratio_positive"
    ] = bool(
        (
            master[
                "median_mfe_mae_ratio"
            ]
            > 0
        ).all()
    )

    for column in [
        "target_2_5_first_vs_stop_2_0_pct",
        "target_2_5_first_vs_stop_2_5_pct",
        "target_2_5_first_vs_stop_3_0_pct",
        "trail30_resolved_pct",
        "trail30_ambiguous_pct",
        "trail30_not_triggered_24h_pct",
    ]:
        if column in master.columns:
            checks[
                f"{column}_valid_percentage"
            ] = bool(
                master[
                    column
                ].between(
                    0,
                    100,
                ).all()
            )

    # ---------------------------------------------------------
    # Report
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
        / "average_comparison_master_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    failed = report[
        report["pass"]
        == False
    ]

    print(
        "\n"
        + "=" * 80
    )

    print(
        "AVERAGE COMPARISON MASTER VALIDATION"
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
        "\nReport saved:"
    )

    print(
        output_file
    )

    print(
        f"\nChecks: {len(report)}"
    )

    print(
        f"Passed: {int(report['pass'].sum())}"
    )

    print(
        f"Failed: {int((~report['pass']).sum())}"
    )


if __name__ == "__main__":
    main()
