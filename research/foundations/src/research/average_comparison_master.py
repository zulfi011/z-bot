from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RESULTS_DIR = Path("results/tables")
OUTPUT_FILE = RESULTS_DIR / "average_comparison_master.csv"


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


def load_csv(filename: str) -> pd.DataFrame:
    path = RESULTS_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Missing required file: {path}"
        )

    return pd.read_csv(path)


def make_base_setups() -> pd.DataFrame:

    rows = []

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            for average_type in ["7d", "15d", "30d"]:
                for touch_zone in [0.5, 1.0, 1.5]:

                    rows.append(
                        {
                            "asset": symbol,
                            "timeframe": timeframe,
                            "average_type": average_type,
                            "touch_zone": touch_zone,
                        }
                    )

    return pd.DataFrame(rows)


def prepare_profit_reach() -> pd.DataFrame:

    df = load_csv(
        "profit_reach_statistics.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    # Keep +2.5% only.
    possible_target_columns = [
        "profit_level_pct",
        "target_pct",
        "profit_level",
    ]

    target_column = None

    for column in possible_target_columns:
        if column in df.columns:
            target_column = column
            break

    if target_column is None:
        raise ValueError(
            "Could not find profit target column "
            "in profit_reach_statistics.csv"
        )

    target_values = pd.to_numeric(
        df[target_column],
        errors="coerce",
    )

    # Handle files where 2.5 may be stored as 0.025.
    if target_values.max() <= 1:
        target_values = (
            target_values * 100
        )

    df = df[
        target_values.round(6)
        == 2.5
    ].copy()

    rename_map = {}

    candidates = {
        "event_count": [
            "valid_event_count",
            "valid_count",
            "event_count",
            "events",
        ],
        "reach_probability_pct": [
            "reach_probability_pct",
            "probability_pct",
            "reached_pct",
            "reach_pct",
        ],
        "median_time_to_target_minutes": [
            "median_time_minutes",
            "median_time_to_reach_minutes",
            "median_time_to_target_minutes",
        ],
    }

    for new_name, options in candidates.items():
        for option in options:
            if option in df.columns:
                rename_map[
                    option
                ] = new_name
                break

    df = df.rename(
        columns=rename_map
    )

    required = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    keep = required.copy()

    for column in [
        "event_count",
        "reach_probability_pct",
        "median_time_to_target_minutes",
    ]:
        if column in df.columns:
            keep.append(column)

    df = df[
        keep
    ].copy()

    return df


def prepare_downside() -> pd.DataFrame:

    df = load_csv(
        "downside_statistics.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    if "window" not in df.columns:
        raise ValueError(
            "downside_statistics.csv "
            "must contain window"
        )

    df = df[
        df["window"].astype(str)
        == "24h"
    ].copy()

    rename_map = {
        "median_downside_pct": "mae_24h_median_pct",
        "p90_severe_downside_pct": "mae_24h_severe10_pct",
        "p95_severe_downside_pct": "mae_24h_severe5_pct",
        "worst_downside_pct": "mae_24h_worst_pct",
    }

    df = df.rename(
        columns=rename_map
    )

    keep = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
        "mae_24h_median_pct",
        "mae_24h_severe10_pct",
        "mae_24h_severe5_pct",
        "mae_24h_worst_pct",
    ]

    return df[
        keep
    ]


def prepare_upside() -> pd.DataFrame:

    df = load_csv(
        "upside_statistics.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    df = df[
        df["window"].astype(str)
        == "24h"
    ].copy()

    rename_map = {
        "median_upside_pct": "mfe_24h_median_pct",
        "p75_upside_pct": "mfe_24h_p75_pct",
        "p90_upside_pct": "mfe_24h_p90_pct",
        "p95_upside_pct": "mfe_24h_p95_pct",
        "best_upside_pct": "mfe_24h_best_pct",
    }

    df = df.rename(
        columns=rename_map
    )

    keep = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
        "mfe_24h_median_pct",
        "mfe_24h_p75_pct",
        "mfe_24h_p90_pct",
        "mfe_24h_p95_pct",
        "mfe_24h_best_pct",
    ]

    return df[
        keep
    ]


def prepare_mfe_mae_balance() -> pd.DataFrame:

    df = load_csv(
        "max_upside_downside_comparison.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    rename_map = {
        "median_upside_to_downside_ratio":
            "median_mfe_mae_ratio",

        "median_excursion_balance":
            "median_excursion_balance_pct",
    }

    df = df.rename(
        columns=rename_map
    )

    keep = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    for column in [
        "median_mfe_mae_ratio",
        "median_excursion_balance_pct",
    ]:
        if column in df.columns:
            keep.append(column)

    return df[
        keep
    ]


def prepare_first_hit() -> pd.DataFrame:

    df = load_csv(
        "first_hit_statistics.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    wanted_stops = [
        2.0,
        2.5,
        3.0,
    ]

    df = df[
        df["stop_pct"].isin(
            wanted_stops
        )
    ].copy()

    value_column = (
        "target_first_pct_all_confirmed"
    )

    if value_column not in df.columns:
        raise ValueError(
            "Missing target_first_pct_all_confirmed "
            "in first_hit_statistics.csv"
        )

    pivot = df.pivot_table(
        index=[
            "asset",
            "timeframe",
            "average_type",
            "touch_zone",
        ],
        columns="stop_pct",
        values=value_column,
        aggfunc="first",
    ).reset_index()

    rename_map = {
        2.0:
            "target_2_5_first_vs_stop_2_0_pct",

        2.5:
            "target_2_5_first_vs_stop_2_5_pct",

        3.0:
            "target_2_5_first_vs_stop_3_0_pct",
    }

    pivot = pivot.rename(
        columns=rename_map
    )

    return pivot


def prepare_post_activation() -> pd.DataFrame:

    df = load_csv(
        "post_activation_statistics.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    df = df[
        df["window"].astype(str)
        == "24h"
    ].copy()

    rename_map = {
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

    df = df.rename(
        columns=rename_map
    )

    keep = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    for column in rename_map.values():
        if column in df.columns:
            keep.append(column)

    return df[
        keep
    ]


def prepare_trailing_support() -> pd.DataFrame:

    df = load_csv(
        "trailing_outcome_comparison.csv"
    )

    df["average_type"] = normalize_average_type(
        df["average_type"]
    )

    df["touch_zone"] = normalize_touch_zone(
        df["touch_zone"]
    )

    df = df[
        pd.to_numeric(
            df["trail_giveback_pct"],
            errors="coerce",
        ).round(6)
        == 30.0
    ].copy()

    rename_map = {
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

    df = df.rename(
        columns=rename_map
    )

    keep = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    for column in rename_map.values():
        if column in df.columns:
            keep.append(column)

    return df[
        keep
    ]


def merge_table(
    base: pd.DataFrame,
    table: pd.DataFrame,
    name: str,
) -> pd.DataFrame:

    keys = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    duplicates = table.duplicated(
        subset=keys
    ).sum()

    if duplicates > 0:
        raise ValueError(
            f"{name} has "
            f"{duplicates} duplicate setup rows"
        )

    result = base.merge(
        table,
        on=keys,
        how="left",
        validate="one_to_one",
    )

    return result


def main():

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Building base setup table..."
    )

    master = make_base_setups()

    print(
        f"Base rows: {len(master)}"
    )

    sources = [
        (
            "profit reach",
            prepare_profit_reach(),
        ),
        (
            "downside",
            prepare_downside(),
        ),
        (
            "upside",
            prepare_upside(),
        ),
        (
            "MFE/MAE balance",
            prepare_mfe_mae_balance(),
        ),
        (
            "first-hit",
            prepare_first_hit(),
        ),
        (
            "post activation",
            prepare_post_activation(),
        ),
        (
            "30% trailing support",
            prepare_trailing_support(),
        ),
    ]

    for name, table in sources:

        print(
            f"Merging {name}: "
            f"{len(table)} rows"
        )

        master = merge_table(
            master,
            table,
            name,
        )

    # ---------------------------------------------------------
    # Final sanity checks
    # ---------------------------------------------------------

    if len(master) != 81:
        raise ValueError(
            f"Expected 81 setup rows, "
            f"got {len(master)}"
        )

    if master[
        [
            "asset",
            "timeframe",
            "average_type",
            "touch_zone",
        ]
    ].duplicated().any():

        raise ValueError(
            "Master table contains duplicate setups"
        )

    master = (
        master
        .sort_values(
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    master.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_FILE
    )

    print(
        f"\nRows: {len(master)}"
    )

    print(
        f"Columns: {len(master.columns)}"
    )

    print(
        "\nMissing values by metric:"
    )

    missing = (
        master
        .isna()
        .sum()
    )

    missing = missing[
        missing > 0
    ]

    if len(
        missing
    ) == 0:

        print(
            "None"
        )

    else:

        print(
            missing.to_string()
        )

    # ---------------------------------------------------------
    # Quick per-average summary
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 110
    )

    print(
        "AVERAGE-LEVEL QUICK SUMMARY"
    )

    print(
        "=" * 110
    )

    summary_columns = []

    for column in [
        "event_count",
        "reach_probability_pct",
        "mae_24h_median_pct",
        "mfe_24h_median_pct",
        "median_mfe_mae_ratio",
        "target_2_5_first_vs_stop_2_5_pct",
        "post_activation_median_extra_upside_24h_pct",
        "trail30_median_realized_return_pct",
    ]:
        if column in master.columns:
            summary_columns.append(
                column
            )

    summary = (
        master
        .groupby(
            "average_type"
        )[
            summary_columns
        ]
        .median(
            numeric_only=True
        )
    )

    print(
        summary.to_string()
    )


if __name__ == "__main__":
    main()