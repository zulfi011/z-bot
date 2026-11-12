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


def validate_dataset(
    symbol: str,
    timeframe: str,
) -> dict:

    print(f"\nValidating {symbol} {timeframe}")

    source_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_first_hit.parquet"
    )

    result_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_post_activation.parquet"
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

    source[
        "target_2_5_first_hit_timestamp"
    ] = pd.to_datetime(
        source[
            "target_2_5_first_hit_timestamp"
        ],
        utc=True,
    )

    result[
        "target_2_5_first_hit_timestamp"
    ] = pd.to_datetime(
        result[
            "target_2_5_first_hit_timestamp"
        ],
        utc=True,
    )

    raw["open_time"] = pd.to_datetime(
        raw["open_time"],
        utc=True,
    )

    raw = (
        raw
        .sort_values("open_time")
        .drop_duplicates(
            subset=["open_time"]
        )
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
        "trailing_activation_reached",
        "trailing_activation_timestamp",
        "trailing_activation_price",
        "post_activation_start_timestamp",
    ]

    for window in WINDOWS:
        required_columns.extend(
            [
                f"post_activation_window_complete_{window}",
                f"post_activation_peak_price_{window}",
                f"extra_upside_after_activation_{window}_pct",
                f"post_activation_peak_timestamp_{window}",
                f"time_to_post_activation_peak_{window}_minutes",
                f"post_peak_retracement_available_{window}",
                f"lowest_price_after_peak_{window}",
                f"max_retracement_from_peak_{window}_pct",
                f"max_retracement_from_peak_timestamp_{window}",
                f"time_from_peak_to_max_retracement_{window}_minutes",
            ]
        )

    checks["required_columns"] = all(
        column in result.columns
        for column in required_columns
    )

    # ---------------------------------------------------------
    # Work on unique underlying touch observations
    # ---------------------------------------------------------

    unique = (
        result
        .drop_duplicates(
            subset=[
                "timestamp",
                "price",
                "target_2_5_price",
                "target_2_5_first_hit_timestamp",
            ]
        )
        .reset_index(drop=True)
    )

    raw_times = pd.DatetimeIndex(
        raw["open_time"]
    )

    highs = raw[
        "high"
    ].to_numpy(
        dtype=np.float64
    )

    lows = raw[
        "low"
    ].to_numpy(
        dtype=np.float64
    )

    activated = (
        unique[
            "target_2_5_first_hit_timestamp"
        ].notna()
    )

    checks[
        "activation_flag_correct"
    ] = (
        unique[
            "trailing_activation_reached"
        ]
        .astype(bool)
        .equals(
            activated
        )
    )

    expected_activation_timestamp = (
        unique[
            "target_2_5_first_hit_timestamp"
        ]
    )

    actual_activation_timestamp = pd.to_datetime(
        unique[
            "trailing_activation_timestamp"
        ],
        utc=True,
    )

    checks[
        "activation_timestamp_correct"
    ] = (
        expected_activation_timestamp
        .reset_index(drop=True)
        .equals(
            actual_activation_timestamp
            .reset_index(drop=True)
        )
    )

    expected_activation_price = (
        unique[
            "target_2_5_price"
        ]
    )

    actual_activation_price = (
        unique[
            "trailing_activation_price"
        ]
    )

    checks[
        "activation_price_correct"
    ] = bool(
        (
            (
                expected_activation_price.isna()
                & actual_activation_price.isna()
            )
            |
            np.isclose(
                expected_activation_price.fillna(0),
                actual_activation_price.fillna(0),
                rtol=1e-12,
                atol=1e-12,
            )
        ).all()
    )

    # ---------------------------------------------------------
    # Post-activation must begin on the NEXT raw 1m candle
    # ---------------------------------------------------------

    expected_post_start = pd.Series(
        pd.NaT,
        index=unique.index,
        dtype="datetime64[us, UTC]",
    )

    expected_post_start.loc[
        activated
    ] = (
        unique.loc[
            activated,
            "target_2_5_first_hit_timestamp",
        ]
        + pd.Timedelta("1min")
    )

    actual_post_start = pd.to_datetime(
        unique[
            "post_activation_start_timestamp"
        ],
        utc=True,
    )

    checks[
        "post_activation_start_correct"
    ] = (
        expected_post_start
        .reset_index(drop=True)
        .equals(
            actual_post_start
            .reset_index(drop=True)
        )
    )

    start_indices = np.full(
        len(unique),
        -1,
        dtype=np.int64,
    )

    activated_positions = np.flatnonzero(
        activated.to_numpy()
    )

    if len(activated_positions) > 0:
        start_indices[
            activated_positions
        ] = raw_times.get_indexer(
            expected_post_start.iloc[
                activated_positions
            ]
        )

    # ---------------------------------------------------------
    # Validate each post-activation window by direct raw scan
    # ---------------------------------------------------------

    for (
        window_name,
        window_minutes,
    ) in WINDOWS.items():

        print(
            f"  Checking {window_name}"
        )

        complete_column = (
            f"post_activation_window_complete_{window_name}"
        )

        peak_price_column = (
            f"post_activation_peak_price_{window_name}"
        )

        extra_upside_column = (
            f"extra_upside_after_activation_{window_name}_pct"
        )

        peak_timestamp_column = (
            f"post_activation_peak_timestamp_{window_name}"
        )

        peak_time_column = (
            f"time_to_post_activation_peak_{window_name}_minutes"
        )

        retracement_available_column = (
            f"post_peak_retracement_available_{window_name}"
        )

        lowest_after_peak_column = (
            f"lowest_price_after_peak_{window_name}"
        )

        retracement_column = (
            f"max_retracement_from_peak_{window_name}_pct"
        )

        retracement_timestamp_column = (
            f"max_retracement_from_peak_timestamp_{window_name}"
        )

        retracement_time_column = (
            f"time_from_peak_to_max_retracement_{window_name}_minutes"
        )

        requested_end = (
            start_indices
            + window_minutes
            - 1
        )

        expected_complete = (
            activated.to_numpy()
            & (start_indices >= 0)
            & (
                requested_end
                < len(raw)
            )
        )

        actual_complete_series = (
            unique[
                complete_column
            ].astype("boolean")
        )

        actual_complete = (
            actual_complete_series
            .fillna(False)
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

        # Non-activated rows should have NA completion flag.
        checks[
            f"{window_name}_nonactivated_complete_na"
        ] = bool(
            actual_complete_series[
                ~activated
            ].isna().all()
        )

        expected_peak = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        expected_peak_index = np.full(
            len(unique),
            -1,
            dtype=np.int64,
        )

        expected_low_after_peak = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        expected_low_after_peak_index = np.full(
            len(unique),
            -1,
            dtype=np.int64,
        )

        complete_positions = np.flatnonzero(
            expected_complete
        )

        for position in complete_positions:

            start = start_indices[
                position
            ]

            end = requested_end[
                position
            ]

            window_highs = highs[
                start:end + 1
            ]

            relative_peak = int(
                np.argmax(
                    window_highs
                )
            )

            peak_index = (
                start
                + relative_peak
            )

            expected_peak[
                position
            ] = highs[
                peak_index
            ]

            expected_peak_index[
                position
            ] = peak_index

            # Retracement is measured only after the peak candle.
            if peak_index < end:

                retracement_lows = lows[
                    peak_index + 1:
                    end + 1
                ]

                relative_low = int(
                    np.argmin(
                        retracement_lows
                    )
                )

                low_index = (
                    peak_index
                    + 1
                    + relative_low
                )

                expected_low_after_peak[
                    position
                ] = lows[
                    low_index
                ]

                expected_low_after_peak_index[
                    position
                ] = low_index

        actual_peak = (
            unique[
                peak_price_column
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        peak_match = (
            (
                np.isnan(expected_peak)
                & np.isnan(actual_peak)
            )
            |
            np.isclose(
                np.nan_to_num(
                    expected_peak
                ),
                np.nan_to_num(
                    actual_peak
                ),
                rtol=1e-12,
                atol=1e-12,
            )
        )

        checks[
            f"{window_name}_peak_price_correct"
        ] = bool(
            peak_match.all()
        )

        activation_prices = (
            unique[
                "trailing_activation_price"
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        expected_extra_upside = (
            (
                expected_peak
                - activation_prices
            )
            / activation_prices
            * 100
        )

        actual_extra_upside = (
            unique[
                extra_upside_column
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        upside_match = (
            (
                np.isnan(
                    expected_extra_upside
                )
                & np.isnan(
                    actual_extra_upside
                )
            )
            |
            np.isclose(
                np.nan_to_num(
                    expected_extra_upside
                ),
                np.nan_to_num(
                    actual_extra_upside
                ),
                rtol=1e-10,
                atol=1e-10,
            )
        )

        checks[
            f"{window_name}_extra_upside_correct"
        ] = bool(
            upside_match.all()
        )

        expected_peak_timestamps = pd.Series(
            pd.NaT,
            index=unique.index,
            dtype="datetime64[us, UTC]",
        )

        if len(
            complete_positions
        ) > 0:
            expected_peak_timestamps.iloc[
                complete_positions
            ] = raw_times[
                expected_peak_index[
                    complete_positions
                ]
            ]

        actual_peak_timestamps = pd.to_datetime(
            unique[
                peak_timestamp_column
            ],
            utc=True,
        )

        checks[
            f"{window_name}_peak_timestamp_correct"
        ] = (
            expected_peak_timestamps
            .reset_index(drop=True)
            .equals(
                actual_peak_timestamps
                .reset_index(drop=True)
            )
        )

        expected_peak_time = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        if len(
            complete_positions
        ) > 0:
            expected_peak_time[
                complete_positions
            ] = (
                expected_peak_index[
                    complete_positions
                ]
                - start_indices[
                    complete_positions
                ]
                + 1
            )

        actual_peak_time = (
            unique[
                peak_time_column
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        peak_time_match = (
            (
                np.isnan(
                    expected_peak_time
                )
                & np.isnan(
                    actual_peak_time
                )
            )
            |
            np.isclose(
                np.nan_to_num(
                    expected_peak_time
                ),
                np.nan_to_num(
                    actual_peak_time
                ),
                rtol=0,
                atol=0,
            )
        )

        checks[
            f"{window_name}_peak_time_correct"
        ] = bool(
            peak_time_match.all()
        )

        # -----------------------------------------------------
        # Retracement availability
        # -----------------------------------------------------

        expected_retracement_available = (
            expected_complete
            & (
                expected_peak_index
                < requested_end
            )
        )

        actual_retracement_series = (
            unique[
                retracement_available_column
            ].astype("boolean")
        )

        actual_retracement_available = (
            actual_retracement_series
            .fillna(False)
            .to_numpy(dtype=bool)
        )

        checks[
            f"{window_name}_retracement_availability_correct"
        ] = bool(
            np.array_equal(
                expected_retracement_available,
                actual_retracement_available,
            )
        )

        checks[
            f"{window_name}_nonactivated_retracement_na"
        ] = bool(
            actual_retracement_series[
                ~activated
            ].isna().all()
        )

        actual_low_after_peak = (
            unique[
                lowest_after_peak_column
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        low_match = (
            (
                np.isnan(
                    expected_low_after_peak
                )
                & np.isnan(
                    actual_low_after_peak
                )
            )
            |
            np.isclose(
                np.nan_to_num(
                    expected_low_after_peak
                ),
                np.nan_to_num(
                    actual_low_after_peak
                ),
                rtol=1e-12,
                atol=1e-12,
            )
        )

        checks[
            f"{window_name}_lowest_after_peak_correct"
        ] = bool(
            low_match.all()
        )

        expected_retracement = (
            (
                expected_low_after_peak
                - expected_peak
            )
            / expected_peak
            * 100
        )

        actual_retracement = (
            unique[
                retracement_column
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        retracement_match = (
            (
                np.isnan(
                    expected_retracement
                )
                & np.isnan(
                    actual_retracement
                )
            )
            |
            np.isclose(
                np.nan_to_num(
                    expected_retracement
                ),
                np.nan_to_num(
                    actual_retracement
                ),
                rtol=1e-10,
                atol=1e-10,
            )
        )

        checks[
            f"{window_name}_retracement_correct"
        ] = bool(
            retracement_match.all()
        )

        expected_retracement_timestamps = pd.Series(
            pd.NaT,
            index=unique.index,
            dtype="datetime64[us, UTC]",
        )

        retracement_positions = np.flatnonzero(
            expected_retracement_available
        )

        if len(
            retracement_positions
        ) > 0:

            expected_retracement_timestamps.iloc[
                retracement_positions
            ] = raw_times[
                expected_low_after_peak_index[
                    retracement_positions
                ]
            ]

        actual_retracement_timestamps = pd.to_datetime(
            unique[
                retracement_timestamp_column
            ],
            utc=True,
        )

        checks[
            f"{window_name}_retracement_timestamp_correct"
        ] = (
            expected_retracement_timestamps
            .reset_index(drop=True)
            .equals(
                actual_retracement_timestamps
                .reset_index(drop=True)
            )
        )

        expected_retracement_time = np.full(
            len(unique),
            np.nan,
            dtype=np.float64,
        )

        if len(
            retracement_positions
        ) > 0:

            expected_retracement_time[
                retracement_positions
            ] = (
                expected_low_after_peak_index[
                    retracement_positions
                ]
                - expected_peak_index[
                    retracement_positions
                ]
            )

        actual_retracement_time = (
            unique[
                retracement_time_column
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        retracement_time_match = (
            (
                np.isnan(
                    expected_retracement_time
                )
                & np.isnan(
                    actual_retracement_time
                )
            )
            |
            np.isclose(
                np.nan_to_num(
                    expected_retracement_time
                ),
                np.nan_to_num(
                    actual_retracement_time
                ),
                rtol=0,
                atol=0,
            )
        )

        checks[
            f"{window_name}_retracement_time_correct"
        ] = bool(
            retracement_time_match.all()
        )

        # -----------------------------------------------------
        # Sanity ranges
        # -----------------------------------------------------

        if len(
            complete_positions
        ) > 0:

            valid_peak_times = (
                actual_peak_time[
                    complete_positions
                ]
            )

            checks[
                f"{window_name}_peak_time_range_valid"
            ] = bool(
                (
                    (valid_peak_times >= 1)
                    &
                    (
                        valid_peak_times
                        <= window_minutes
                    )
                ).all()
            )

        else:

            checks[
                f"{window_name}_peak_time_range_valid"
            ] = True

        if len(
            retracement_positions
        ) > 0:

            valid_retracement_times = (
                actual_retracement_time[
                    retracement_positions
                ]
            )

            checks[
                f"{window_name}_retracement_time_positive"
            ] = bool(
                (
                    valid_retracement_times
                    >= 1
                ).all()
            )

        else:

            checks[
                f"{window_name}_retracement_time_positive"
            ] = True

    # ---------------------------------------------------------
    # Window nesting
    #
    # Longer windows cannot have lower post-activation peaks.
    # ---------------------------------------------------------

    checks[
        "post_activation_peaks_nested"
    ] = True

    comparable = (
        unique[
            "post_activation_window_complete_24h"
        ]
        .astype("boolean")
        .fillna(False)
    )

    if comparable.any():

        peak_1h = unique.loc[
            comparable,
            "post_activation_peak_price_1h",
        ]

        peak_4h = unique.loc[
            comparable,
            "post_activation_peak_price_4h",
        ]

        peak_24h = unique.loc[
            comparable,
            "post_activation_peak_price_24h",
        ]

        invalid = (
            (peak_4h < peak_1h)
            |
            (peak_24h < peak_4h)
        )

        checks[
            "post_activation_peaks_nested"
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
        bool(
            checks[key]
        )
        for key in boolean_checks
    )

    print(
        "  RESULT:",
        "PASS"
        if checks["overall_pass"]
        else "FAIL",
    )

    if not checks[
        "overall_pass"
    ]:

        print(
            "  Failed checks:"
        )

        for key in boolean_checks:

            if not checks[key]:

                print(
                    f"    - {key}"
                )

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
        / "post_activation_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    print(
        "\n----------------------------------------"
    )

    print(
        "POST-ACTIVATION VALIDATION"
    )

    print(
        "----------------------------------------"
    )

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

    print(
        "\nReport saved:"
    )

    print(
        output_file
    )

    print(
        "\nOVERALL RESULT:"
    )

    if overall:
        print(
            "PASS"
        )

    else:
        print(
            "FAIL"
        )


if __name__ == "__main__":
    main()
