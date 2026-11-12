from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")
REPORT_DIR = Path("results/reports")


PROFIT_LEVELS = {
    "0_5": 0.005,
    "1_0": 0.010,
    "1_5": 0.015,
    "2_0": 0.020,
    "2_5": 0.025,
    "3_0": 0.030,
    "5_0": 0.050,
}

LEVEL_ORDER = [
    "0_5",
    "1_0",
    "1_5",
    "2_0",
    "2_5",
    "3_0",
    "5_0",
]

OBSERVATION_MINUTES = 24 * 60


def build_sparse_max_table(values: np.ndarray):
    """
    Sparse table used only for efficient validation of arbitrary
    raw 1-minute high ranges.
    """

    n = len(values)

    max_power = int(np.floor(np.log2(n)))

    table = [values.astype(np.float64)]

    for k in range(1, max_power + 1):

        previous = table[k - 1]

        half = 1 << (k - 1)
        length = n - (1 << k) + 1

        current = np.maximum(
            previous[:length],
            previous[half:half + length],
        )

        table.append(current)

    return table


def range_max(
    sparse_table,
    left: np.ndarray,
    right: np.ndarray,
):
    """
    Inclusive range maximum for arrays of [left, right].
    """

    result = np.full(
        len(left),
        np.nan,
        dtype=np.float64,
    )

    valid = (
        (left >= 0)
        & (right >= left)
    )

    if not valid.any():
        return result

    positions = np.flatnonzero(valid)

    lengths = (
        right[positions]
        - left[positions]
        + 1
    )

    powers = np.floor(
        np.log2(lengths)
    ).astype(np.int64)

    for power in np.unique(powers):

        mask = powers == power

        current_positions = positions[mask]

        block_size = 1 << power

        left_values = sparse_table[power][
            left[current_positions]
        ]

        second_start = (
            right[current_positions]
            - block_size
            + 1
        )

        right_values = sparse_table[power][
            second_start
        ]

        result[current_positions] = np.maximum(
            left_values,
            right_values,
        )

    return result


def validate_dataset(
    symbol: str,
    timeframe: str,
):

    print(f"\nValidating {symbol} {timeframe}")

    part12_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_returns.parquet"
    )

    part13_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_profit_reach.parquet"
    )

    raw_file = (
        RAW_DIR
        / symbol
        / f"{symbol}_1m.parquet"
    )

    checks = {}

    checks["part12_file_exists"] = part12_file.exists()
    checks["part13_file_exists"] = part13_file.exists()
    checks["raw_file_exists"] = raw_file.exists()

    if not all(
        [
            checks["part12_file_exists"],
            checks["part13_file_exists"],
            checks["raw_file_exists"],
        ]
    ):
        checks["overall_pass"] = False
        return checks

    # ---------------------------------------------------------
    # Load
    # ---------------------------------------------------------

    part12 = pd.read_parquet(part12_file)

    result = pd.read_parquet(part13_file)

    raw = pd.read_parquet(
        raw_file,
        columns=[
            "open_time",
            "high",
        ],
    )

    part12["timestamp"] = pd.to_datetime(
        part12["timestamp"],
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
        raw.sort_values("open_time")
        .drop_duplicates(subset=["open_time"])
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Basic integrity
    # ---------------------------------------------------------

    checks["row_count_match"] = (
        len(part12) == len(result)
    )

    checks["event_ids_unique"] = (
        result["event_id"].duplicated().sum() == 0
    )

    checks["event_ids_match"] = (
        set(part12["event_id"])
        == set(result["event_id"])
    )

    part12_sorted = (
        part12
        .sort_values("event_id")
        .reset_index(drop=True)
    )

    result_sorted = (
        result
        .sort_values("event_id")
        .reset_index(drop=True)
    )

    checks["part12_data_preserved"] = (
        part12_sorted.equals(
            result_sorted[
                part12_sorted.columns
            ]
        )
    )

    required_columns = [
        "observation_complete_24h",
        "observation_start_timestamp",
    ]

    for level in LEVEL_ORDER:

        required_columns.extend(
            [
                f"target_price_{level}_pct",
                f"reached_{level}_pct",
                f"first_reached_{level}_pct_timestamp",
                f"time_to_{level}_pct_minutes",
            ]
        )

    checks["required_columns"] = all(
        column in result.columns
        for column in required_columns
    )

    # ---------------------------------------------------------
    # Work only on unique touch candle/price observations
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

    checks["duplicate_classifications_consistent"] = True

    grouped = result.groupby(
        [
            "timestamp",
            "price",
        ],
        sort=False,
        dropna=False,
    )

    comparison_columns = required_columns

    consistency = grouped[
        comparison_columns
    ].nunique(
        dropna=False
    )

    if (consistency > 1).any().any():
        checks[
            "duplicate_classifications_consistent"
        ] = False

    # ---------------------------------------------------------
    # Raw arrays
    # ---------------------------------------------------------

    raw_times = pd.DatetimeIndex(
        raw["open_time"]
    )

    highs = raw["high"].to_numpy(
        dtype=np.float64
    )

    sparse_table = build_sparse_max_table(
        highs
    )

    timeframe_delta = pd.Timedelta(
        timeframe
    )

    expected_start = (
        unique["timestamp"]
        + timeframe_delta
    )

    checks["observation_start_correct"] = (
        expected_start.reset_index(drop=True)
        .equals(
            pd.to_datetime(
                unique["observation_start_timestamp"],
                utc=True,
            ).reset_index(drop=True)
        )
    )

    start_indices = raw_times.get_indexer(
        expected_start
    )

    requested_end_indices = (
        start_indices
        + OBSERVATION_MINUTES
        - 1
    )

    expected_complete = (
        (start_indices >= 0)
        & (
            requested_end_indices
            < len(raw)
        )
    )

    actual_complete = (
        unique["observation_complete_24h"]
        .to_numpy(dtype=bool)
    )

    checks["observation_complete_correct"] = bool(
        np.array_equal(
            expected_complete,
            actual_complete,
        )
    )

    actual_end_indices = np.minimum(
        requested_end_indices,
        len(raw) - 1,
    )

    actual_end_indices[
        start_indices < 0
    ] = -1

    # ---------------------------------------------------------
    # Validate every target level
    # ---------------------------------------------------------

    for level_name, level_pct in PROFIT_LEVELS.items():

        print(
            f"  Checking +{level_pct * 100:g}%"
        )

        target_column = (
            f"target_price_{level_name}_pct"
        )

        reached_column = (
            f"reached_{level_name}_pct"
        )

        hit_timestamp_column = (
            f"first_reached_{level_name}_pct_timestamp"
        )

        time_column = (
            f"time_to_{level_name}_pct_minutes"
        )

        # -----------------------------------------------------
        # Target price
        # -----------------------------------------------------

        expected_target = (
            unique["price"].to_numpy(
                dtype=np.float64
            )
            * (1 + level_pct)
        )

        actual_target = (
            unique[target_column]
            .to_numpy(dtype=np.float64)
        )

        checks[
            f"{level_name}_target_price_correct"
        ] = bool(
            np.isclose(
                expected_target,
                actual_target,
                rtol=1e-12,
                atol=1e-12,
            ).all()
        )

        # -----------------------------------------------------
        # Maximum high available inside observation
        # -----------------------------------------------------

        future_max = range_max(
            sparse_table,
            start_indices,
            actual_end_indices,
        )

        hit_exists = (
            future_max
            >= expected_target
        )

        reached_series = unique[
            reached_column
        ].astype("boolean")

        actual_true = (
            reached_series
            .fillna(False)
            .to_numpy(dtype=bool)
        )

        actual_na = (
            reached_series
            .isna()
            .to_numpy()
        )

        actual_false = (
            (~actual_true)
            & (~actual_na)
        )

        # True iff target was observed
        checks[
            f"{level_name}_true_correct"
        ] = bool(
            np.array_equal(
                actual_true,
                hit_exists,
            )
        )

        # False iff full 24h exists and no hit
        expected_false = (
            expected_complete
            & (~hit_exists)
        )

        checks[
            f"{level_name}_false_correct"
        ] = bool(
            np.array_equal(
                actual_false,
                expected_false,
            )
        )

        # NA iff incomplete 24h and no hit
        expected_na = (
            (~expected_complete)
            & (~hit_exists)
        )

        checks[
            f"{level_name}_unknown_correct"
        ] = bool(
            np.array_equal(
                actual_na,
                expected_na,
            )
        )

        # -----------------------------------------------------
        # Validate first-hit timestamp and time
        # -----------------------------------------------------

        hit_timestamp = pd.to_datetime(
            unique[hit_timestamp_column],
            utc=True,
        )

        time_to_hit = unique[
            time_column
        ]

        true_positions = np.flatnonzero(
            actual_true
        )

        hit_index = np.full(
            len(unique),
            -1,
            dtype=np.int64,
        )

        if len(true_positions) > 0:

            hit_index[
                true_positions
            ] = raw_times.get_indexer(
                hit_timestamp.iloc[
                    true_positions
                ]
            )

        valid_hit_indices = (
            hit_index[true_positions] >= 0
        )

        checks[
            f"{level_name}_hit_timestamp_exists_in_raw"
        ] = bool(
            valid_hit_indices.all()
        )

        # -----------------------------------------------------
        # High at first-hit candle must reach target
        # -----------------------------------------------------

        if len(true_positions) > 0:

            observed_high = highs[
                hit_index[true_positions]
            ]

            checks[
                f"{level_name}_hit_candle_reaches_target"
            ] = bool(
                (
                    observed_high
                    >= expected_target[
                        true_positions
                    ]
                ).all()
            )

        else:

            checks[
                f"{level_name}_hit_candle_reaches_target"
            ] = True

        # -----------------------------------------------------
        # There must be no earlier target hit.
        # -----------------------------------------------------

        if len(true_positions) > 0:

            previous_end = (
                hit_index[true_positions]
                - 1
            )

            previous_max = range_max(
                sparse_table,
                start_indices[
                    true_positions
                ],
                previous_end,
            )

            has_previous_range = (
                previous_end
                >= start_indices[
                    true_positions
                ]
            )

            earlier_hit = np.zeros(
                len(true_positions),
                dtype=bool,
            )

            earlier_hit[
                has_previous_range
            ] = (
                previous_max[
                    has_previous_range
                ]
                >= expected_target[
                    true_positions[
                        has_previous_range
                    ]
                ]
            )

            checks[
                f"{level_name}_first_hit_is_first"
            ] = not bool(
                earlier_hit.any()
            )

        else:

            checks[
                f"{level_name}_first_hit_is_first"
            ] = True

        # -----------------------------------------------------
        # Time-to-hit formula
        # -----------------------------------------------------

        expected_time = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        if len(true_positions) > 0:

            expected_time[
                true_positions
            ] = (
                hit_index[
                    true_positions
                ]
                - start_indices[
                    true_positions
                ]
                + 1
            )

        actual_time = (
            time_to_hit.to_numpy(
                dtype=np.float64,
                na_value=np.nan,
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
            f"{level_name}_time_correct"
        ] = bool(
            time_match.all()
        )

        # Non-hit rows must not have timestamp
        checks[
            f"{level_name}_nonhit_timestamp_empty"
        ] = bool(
            hit_timestamp[
                ~actual_true
            ].isna().all()
        )

        checks[
            f"{level_name}_nonhit_time_empty"
        ] = bool(
            time_to_hit[
                ~actual_true
            ].isna().all()
        )

        if len(true_positions) > 0:

            checks[
                f"{level_name}_time_range_valid"
            ] = bool(
                (
                    (
                        actual_time[
                            true_positions
                        ]
                        >= 1
                    )
                    &
                    (
                        actual_time[
                            true_positions
                        ]
                        <= OBSERVATION_MINUTES
                    )
                ).all()
            )

        else:

            checks[
                f"{level_name}_time_range_valid"
            ] = True

    # ---------------------------------------------------------
    # Nested level validation
    # ---------------------------------------------------------

    checks["reach_levels_nested"] = True
    checks["higher_targets_not_reached_earlier"] = True

    for lower, higher in zip(
        LEVEL_ORDER[:-1],
        LEVEL_ORDER[1:],
    ):

        lower_reached = (
            unique[
                f"reached_{lower}_pct"
            ]
            .astype("boolean")
        )

        higher_reached = (
            unique[
                f"reached_{higher}_pct"
            ]
            .astype("boolean")
        )

        # Higher target True requires lower target True.
        invalid_nested = (
            higher_reached.fillna(False)
            & ~lower_reached.fillna(False)
        )

        if invalid_nested.any():

            checks[
                "reach_levels_nested"
            ] = False

        lower_time = unique[
            f"time_to_{lower}_pct_minutes"
        ]

        higher_time = unique[
            f"time_to_{higher}_pct_minutes"
        ]

        both_reached = (
            lower_reached.fillna(False)
            & higher_reached.fillna(False)
        )

        invalid_time = (
            higher_time[
                both_reached
            ]
            <
            lower_time[
                both_reached
            ]
        )

        if invalid_time.any():

            checks[
                "higher_targets_not_reached_earlier"
            ] = False

    # ---------------------------------------------------------
    # Deterministic direct-scanning spot check
    # ---------------------------------------------------------

    checks["direct_scan_sample_pass"] = True

    if len(unique) > 0:

        sample_size = min(
            200,
            len(unique),
        )

        sample_indices = np.linspace(
            0,
            len(unique) - 1,
            sample_size,
            dtype=int,
        )

        for row_index in sample_indices:

            start = start_indices[
                row_index
            ]

            end = actual_end_indices[
                row_index
            ]

            if start < 0 or end < start:
                continue

            window_highs = highs[
                start:end + 1
            ]

            for level_name, level_pct in PROFIT_LEVELS.items():

                target = (
                    float(
                        unique.loc[
                            row_index,
                            "price",
                        ]
                    )
                    * (1 + level_pct)
                )

                hits = np.flatnonzero(
                    window_highs >= target
                )

                recorded = unique.loc[
                    row_index,
                    f"reached_{level_name}_pct",
                ]

                if len(hits) > 0:

                    if recorded is not True and recorded != True:
                        checks[
                            "direct_scan_sample_pass"
                        ] = False
                        break

                    expected_minutes = (
                        int(hits[0]) + 1
                    )

                    recorded_minutes = (
                        unique.loc[
                            row_index,
                            f"time_to_{level_name}_pct_minutes",
                        ]
                    )

                    if (
                        recorded_minutes
                        != expected_minutes
                    ):
                        checks[
                            "direct_scan_sample_pass"
                        ] = False
                        break

                else:

                    if expected_complete[
                        row_index
                    ]:

                        if recorded is not False and recorded != False:
                            checks[
                                "direct_scan_sample_pass"
                            ] = False
                            break

                    else:

                        if not pd.isna(recorded):
                            checks[
                                "direct_scan_sample_pass"
                            ] = False
                            break

            if not checks[
                "direct_scan_sample_pass"
            ]:
                break

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

    report = pd.DataFrame(rows)

    output_file = (
        REPORT_DIR
        / "profit_level_reach_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    print("\n----------------------------------------")
    print("PROFIT LEVEL REACH VALIDATION")
    print("----------------------------------------")

    print(
        report[
            [
                "symbol",
                "timeframe",
                "overall_pass",
            ]
        ].to_string(index=False)
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