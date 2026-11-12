from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")
REPORT_DIR = Path("results/reports")


WINDOWS = {
    "1h": 60,
    "4h": 240,
    "24h": 1440,
}


def validate_dataset(symbol: str, timeframe: str) -> dict:

    print(f"\nValidating {symbol} {timeframe}")

    source_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_max_downside.parquet"
    )

    result_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_max_upside.parquet"
    )

    raw_file = (
        RAW_DIR
        / symbol
        / f"{symbol}_1m.parquet"
    )

    checks = {}

    checks["source_exists"] = source_file.exists()
    checks["result_exists"] = result_file.exists()
    checks["raw_exists"] = raw_file.exists()

    if not all(
        [
            checks["source_exists"],
            checks["result_exists"],
            checks["raw_exists"],
        ]
    ):
        checks["overall_pass"] = False
        return checks

    source = pd.read_parquet(source_file)
    result = pd.read_parquet(result_file)

    raw = pd.read_parquet(
        raw_file,
        columns=[
            "open_time",
            "high",
        ],
    )

    source["timestamp"] = pd.to_datetime(
        source["timestamp"],
        utc=True,
    )

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
    )

    raw["open_time"] = pd.to_datetime(
        raw["open_time"],
        utc=True,
    )

    raw = (
        raw
        .sort_values("open_time")
        .drop_duplicates(subset=["open_time"])
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Basic integrity
    # ---------------------------------------------------------

    checks["row_count_match"] = (
        len(source) == len(result)
    )

    checks["event_ids_unique"] = (
        result["event_id"].duplicated().sum() == 0
    )

    checks["event_ids_match"] = (
        set(source["event_id"])
        == set(result["event_id"])
    )

    source_sorted = (
        source
        .sort_values("event_id")
        .reset_index(drop=True)
    )

    result_sorted = (
        result
        .sort_values("event_id")
        .reset_index(drop=True)
    )

    checks["previous_data_preserved"] = (
        source_sorted.equals(
            result_sorted[
                source_sorted.columns
            ]
        )
    )

    required_columns = [
        "upside_observation_start_timestamp",
    ]

    for window in WINDOWS:
        required_columns.extend(
            [
                f"upside_window_complete_{window}",
                f"highest_price_{window}",
                f"max_upside_{window}_pct",
                f"max_upside_{window}_timestamp",
                f"time_to_max_upside_{window}_minutes",
            ]
        )

    checks["required_columns"] = all(
        column in result.columns
        for column in required_columns
    )

    # ---------------------------------------------------------
    # Work on unique touch candles
    # ---------------------------------------------------------

    unique = (
        result
        .drop_duplicates(
            subset=[
                "timestamp",
                "price",
            ]
        )
        .reset_index(drop=True)
    )

    raw_times = pd.DatetimeIndex(
        raw["open_time"]
    )

    highs = raw["high"].to_numpy(
        dtype=np.float64
    )

    timeframe_delta = pd.Timedelta(
        timeframe
    )

    expected_start = (
        unique["timestamp"]
        + timeframe_delta
    )

    recorded_start = pd.to_datetime(
        unique[
            "upside_observation_start_timestamp"
        ],
        utc=True,
    )

    checks["observation_start_correct"] = (
        expected_start.reset_index(drop=True)
        .equals(
            recorded_start.reset_index(drop=True)
        )
    )

    start_indices = raw_times.get_indexer(
        expected_start
    )

    # ---------------------------------------------------------
    # Validate each window
    # ---------------------------------------------------------

    for window_name, window_minutes in WINDOWS.items():

        print(f"  Checking {window_name}")

        complete_column = (
            f"upside_window_complete_{window_name}"
        )

        highest_price_column = (
            f"highest_price_{window_name}"
        )

        upside_column = (
            f"max_upside_{window_name}_pct"
        )

        timestamp_column = (
            f"max_upside_{window_name}_timestamp"
        )

        time_column = (
            f"time_to_max_upside_{window_name}_minutes"
        )

        requested_end = (
            start_indices
            + window_minutes
            - 1
        )

        expected_complete = (
            (start_indices >= 0)
            & (
                requested_end
                < len(raw)
            )
        )

        actual_complete = (
            unique[
                complete_column
            ]
            .to_numpy(dtype=bool)
        )

        checks[
            f"{window_name}_complete_correct"
        ] = bool(
            np.array_equal(
                expected_complete,
                actual_complete,
            )
        )

        # -----------------------------------------------------
        # Independently scan every complete window
        # -----------------------------------------------------

        expected_highest = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        expected_highest_index = np.full(
            len(unique),
            -1,
            dtype=np.int64,
        )

        complete_positions = np.flatnonzero(
            expected_complete
        )

        for position in complete_positions:

            start = start_indices[position]

            end = requested_end[position]

            window_highs = highs[
                start:end + 1
            ]

            relative_index = int(
                np.argmax(window_highs)
            )

            expected_highest[position] = (
                window_highs[
                    relative_index
                ]
            )

            expected_highest_index[position] = (
                start
                + relative_index
            )

        actual_highest = (
            unique[
                highest_price_column
            ]
            .to_numpy(dtype=np.float64)
        )

        highest_match = (
            (
                np.isnan(expected_highest)
                & np.isnan(actual_highest)
            )
            |
            np.isclose(
                np.nan_to_num(expected_highest),
                np.nan_to_num(actual_highest),
                rtol=1e-12,
                atol=1e-12,
            )
        )

        checks[
            f"{window_name}_highest_price_correct"
        ] = bool(
            highest_match.all()
        )

        # -----------------------------------------------------
        # Validate upside formula
        # -----------------------------------------------------

        prices = (
            unique[
                "price"
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        expected_upside = (
            (
                expected_highest
                - prices
            )
            / prices
            * 100
        )

        actual_upside = (
            unique[
                upside_column
            ]
            .to_numpy(dtype=np.float64)
        )

        upside_match = (
            (
                np.isnan(expected_upside)
                & np.isnan(actual_upside)
            )
            |
            np.isclose(
                np.nan_to_num(expected_upside),
                np.nan_to_num(actual_upside),
                rtol=1e-10,
                atol=1e-10,
            )
        )

        checks[
            f"{window_name}_upside_formula_correct"
        ] = bool(
            upside_match.all()
        )

        # -----------------------------------------------------
        # Validate timestamp of first maximum
        # -----------------------------------------------------

        expected_timestamps = pd.Series(
            pd.NaT,
            index=unique.index,
            dtype="datetime64[us, UTC]",
        )

        if len(complete_positions) > 0:

            expected_timestamps.iloc[
                complete_positions
            ] = raw_times[
                expected_highest_index[
                    complete_positions
                ]
            ]

        actual_timestamps = pd.to_datetime(
            unique[
                timestamp_column
            ],
            utc=True,
        )

        checks[
            f"{window_name}_timestamp_correct"
        ] = (
            expected_timestamps.reset_index(drop=True)
            .equals(
                actual_timestamps.reset_index(drop=True)
            )
        )

        # -----------------------------------------------------
        # Validate time to maximum
        # -----------------------------------------------------

        expected_time = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        if len(complete_positions) > 0:

            expected_time[
                complete_positions
            ] = (
                expected_highest_index[
                    complete_positions
                ]
                - start_indices[
                    complete_positions
                ]
                + 1
            )

        actual_time = (
            unique[
                time_column
            ]
            .to_numpy(dtype=np.float64)
        )

        time_match = (
            (
                np.isnan(expected_time)
                & np.isnan(actual_time)
            )
            |
            np.isclose(
                np.nan_to_num(expected_time),
                np.nan_to_num(actual_time),
                rtol=0,
                atol=0,
            )
        )

        checks[
            f"{window_name}_time_correct"
        ] = bool(
            time_match.all()
        )

        # -----------------------------------------------------
        # Incomplete windows must stay empty
        # -----------------------------------------------------

        incomplete = ~expected_complete

        checks[
            f"{window_name}_incomplete_high_empty"
        ] = bool(
            unique.loc[
                incomplete,
                highest_price_column,
            ].isna().all()
        )

        checks[
            f"{window_name}_incomplete_upside_empty"
        ] = bool(
            unique.loc[
                incomplete,
                upside_column,
            ].isna().all()
        )

        checks[
            f"{window_name}_incomplete_timestamp_empty"
        ] = bool(
            pd.to_datetime(
                unique.loc[
                    incomplete,
                    timestamp_column,
                ],
                utc=True,
            ).isna().all()
        )

        checks[
            f"{window_name}_incomplete_time_empty"
        ] = bool(
            unique.loc[
                incomplete,
                time_column,
            ].isna().all()
        )

        # -----------------------------------------------------
        # Time range sanity
        # -----------------------------------------------------

        if len(complete_positions) > 0:

            valid_times = actual_time[
                complete_positions
            ]

            checks[
                f"{window_name}_time_range_valid"
            ] = bool(
                (
                    (valid_times >= 1)
                    &
                    (
                        valid_times
                        <= window_minutes
                    )
                ).all()
            )

        else:

            checks[
                f"{window_name}_time_range_valid"
            ] = True

    # ---------------------------------------------------------
    # Window nesting
    #
    # Highest price over 24h must be >= 4h,
    # and highest over 4h must be >= 1h.
    # ---------------------------------------------------------

    checks["highest_prices_nested"] = True

    comparable = (
        unique[
            "upside_window_complete_24h"
        ]
        .astype(bool)
    )

    if comparable.any():

        highs_1h = unique.loc[
            comparable,
            "highest_price_1h",
        ]

        highs_4h = unique.loc[
            comparable,
            "highest_price_4h",
        ]

        highs_24h = unique.loc[
            comparable,
            "highest_price_24h",
        ]

        invalid = (
            (highs_4h < highs_1h)
            |
            (highs_24h < highs_4h)
        )

        checks[
            "highest_prices_nested"
        ] = not bool(
            invalid.any()
        )

    # ---------------------------------------------------------
    # Overall
    # ---------------------------------------------------------

    boolean_checks = [
        key
        for key, value in checks.items()
        if isinstance(
            value,
            (bool, np.bool_),
        )
    ]

    checks["overall_pass"] = all(
        bool(checks[key])
        for key in boolean_checks
    )

    print(
        "  RESULT:",
        "PASS"
        if checks["overall_pass"]
        else "FAIL",
    )

    if not checks["overall_pass"]:

        print("  Failed checks:")

        for key in boolean_checks:

            if not checks[key]:
                print(f"    - {key}")

    return checks


def main():

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    overall = True

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            checks = validate_dataset(
                symbol,
                timeframe,
            )

            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    **checks,
                }
            )

            if not checks.get(
                "overall_pass",
                False,
            ):
                overall = False

    report = pd.DataFrame(
        rows
    )

    output_file = (
        REPORT_DIR
        / "maximum_upside_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    print("\n----------------------------------------")
    print("MAXIMUM UPSIDE VALIDATION")
    print("----------------------------------------")

    print(
        report[
            [
                "symbol",
                "timeframe",
                "overall_pass",
            ]
        ].to_string(
            index=False
        )
    )

    print("\nReport saved:")
    print(output_file)

    print("\nOVERALL RESULT:")

    if overall:
        print("PASS")
    else:
        print("FAIL")


if __name__ == "__main__":
    main()