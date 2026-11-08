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
        / f"{symbol}_{timeframe}_touch_events_with_profit_reach.parquet"
    )

    result_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_max_downside.parquet"
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
            "low",
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
        "downside_observation_start_timestamp",
    ]

    for window in WINDOWS:
        required_columns.extend(
            [
                f"downside_window_complete_{window}",
                f"lowest_price_{window}",
                f"max_downside_{window}_pct",
                f"max_downside_{window}_timestamp",
                f"time_to_max_downside_{window}_minutes",
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

    lows = raw["low"].to_numpy(
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
            "downside_observation_start_timestamp"
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
    # Validate each window independently
    # ---------------------------------------------------------

    for window_name, window_minutes in WINDOWS.items():

        print(f"  Checking {window_name}")

        complete_column = (
            f"downside_window_complete_{window_name}"
        )

        lowest_price_column = (
            f"lowest_price_{window_name}"
        )

        downside_column = (
            f"max_downside_{window_name}_pct"
        )

        timestamp_column = (
            f"max_downside_{window_name}_timestamp"
        )

        time_column = (
            f"time_to_max_downside_{window_name}_minutes"
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
        # Independently scan each complete window
        # -----------------------------------------------------

        expected_lowest = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        expected_lowest_index = np.full(
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

            window_lows = lows[
                start:end + 1
            ]

            relative_index = int(
                np.argmin(window_lows)
            )

            expected_lowest[position] = (
                window_lows[
                    relative_index
                ]
            )

            expected_lowest_index[position] = (
                start
                + relative_index
            )

        actual_lowest = (
            unique[
                lowest_price_column
            ]
            .to_numpy(dtype=np.float64)
        )

        lowest_match = (
            (
                np.isnan(expected_lowest)
                & np.isnan(actual_lowest)
            )
            |
            np.isclose(
                np.nan_to_num(expected_lowest),
                np.nan_to_num(actual_lowest),
                rtol=1e-12,
                atol=1e-12,
            )
        )

        checks[
            f"{window_name}_lowest_price_correct"
        ] = bool(
            lowest_match.all()
        )

        # -----------------------------------------------------
        # Validate downside formula
        # -----------------------------------------------------

        prices = (
            unique[
                "price"
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        expected_downside = (
            (
                expected_lowest
                - prices
            )
            / prices
            * 100
        )

        actual_downside = (
            unique[
                downside_column
            ]
            .to_numpy(dtype=np.float64)
        )

        downside_match = (
            (
                np.isnan(expected_downside)
                & np.isnan(actual_downside)
            )
            |
            np.isclose(
                np.nan_to_num(expected_downside),
                np.nan_to_num(actual_downside),
                rtol=1e-10,
                atol=1e-10,
            )
        )

        checks[
            f"{window_name}_downside_formula_correct"
        ] = bool(
            downside_match.all()
        )

        # -----------------------------------------------------
        # Validate first timestamp of minimum
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
                expected_lowest_index[
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
        # Validate time-to-minimum
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
                expected_lowest_index[
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
            .to_numpy(
                dtype=np.float64
            )
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
            f"{window_name}_incomplete_low_empty"
        ] = bool(
            unique.loc[
                incomplete,
                lowest_price_column,
            ].isna().all()
        )

        checks[
            f"{window_name}_incomplete_downside_empty"
        ] = bool(
            unique.loc[
                incomplete,
                downside_column,
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
    # Lowest price over 24h must be <= lowest over 4h,
    # which must be <= lowest over 1h.
    # ---------------------------------------------------------

    checks["lowest_prices_nested"] = True

    comparable = (
        unique[
            "downside_window_complete_24h"
        ]
        .astype(bool)
    )

    if comparable.any():

        lows_1h = unique.loc[
            comparable,
            "lowest_price_1h",
        ]

        lows_4h = unique.loc[
            comparable,
            "lowest_price_4h",
        ]

        lows_24h = unique.loc[
            comparable,
            "lowest_price_24h",
        ]

        invalid = (
            (lows_4h > lows_1h)
            |
            (lows_24h > lows_4h)
        )

        checks[
            "lowest_prices_nested"
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
        / "maximum_downside_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    print("\n----------------------------------------")
    print("MAXIMUM DOWNSIDE VALIDATION")
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