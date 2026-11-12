from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")

WINDOWS = {
    "1h": 60,
    "4h": 240,
    "24h": 1440,
}


def build_sparse_max_table(values: np.ndarray):
    """
    Build sparse tables for fast range-maximum queries.

    Stores:
    - maximum value
    - earliest index where that maximum occurs
    """

    n = len(values)

    max_power = int(
        np.floor(
            np.log2(n)
        )
    )

    value_table = [
        values.astype(np.float64)
    ]

    index_table = [
        np.arange(
            n,
            dtype=np.int64,
        )
    ]

    for power in range(
        1,
        max_power + 1,
    ):

        previous_values = (
            value_table[
                power - 1
            ]
        )

        previous_indices = (
            index_table[
                power - 1
            ]
        )

        half = 1 << (
            power - 1
        )

        length = (
            n
            - (1 << power)
            + 1
        )

        left_values = (
            previous_values[
                :length
            ]
        )

        right_values = (
            previous_values[
                half:
                half + length
            ]
        )

        left_indices = (
            previous_indices[
                :length
            ]
        )

        right_indices = (
            previous_indices[
                half:
                half + length
            ]
        )

        choose_left = (
            (left_values > right_values)
            |
            (
                (left_values == right_values)
                &
                (
                    left_indices
                    <= right_indices
                )
            )
        )

        current_values = np.where(
            choose_left,
            left_values,
            right_values,
        )

        current_indices = np.where(
            choose_left,
            left_indices,
            right_indices,
        )

        value_table.append(
            current_values
        )

        index_table.append(
            current_indices
        )

    return (
        value_table,
        index_table,
    )


def build_sparse_min_table(values: np.ndarray):
    """
    Build sparse tables for fast range-minimum queries.

    Stores:
    - minimum value
    - earliest index where that minimum occurs
    """

    n = len(values)

    max_power = int(
        np.floor(
            np.log2(n)
        )
    )

    value_table = [
        values.astype(np.float64)
    ]

    index_table = [
        np.arange(
            n,
            dtype=np.int64,
        )
    ]

    for power in range(
        1,
        max_power + 1,
    ):

        previous_values = (
            value_table[
                power - 1
            ]
        )

        previous_indices = (
            index_table[
                power - 1
            ]
        )

        half = 1 << (
            power - 1
        )

        length = (
            n
            - (1 << power)
            + 1
        )

        left_values = (
            previous_values[
                :length
            ]
        )

        right_values = (
            previous_values[
                half:
                half + length
            ]
        )

        left_indices = (
            previous_indices[
                :length
            ]
        )

        right_indices = (
            previous_indices[
                half:
                half + length
            ]
        )

        choose_left = (
            (left_values < right_values)
            |
            (
                (left_values == right_values)
                &
                (
                    left_indices
                    <= right_indices
                )
            )
        )

        current_values = np.where(
            choose_left,
            left_values,
            right_values,
        )

        current_indices = np.where(
            choose_left,
            left_indices,
            right_indices,
        )

        value_table.append(
            current_values
        )

        index_table.append(
            current_indices
        )

    return (
        value_table,
        index_table,
    )


def range_extreme_with_index(
    value_table,
    index_table,
    left: np.ndarray,
    right: np.ndarray,
    mode: str,
):
    """
    Return range max/min and earliest index for inclusive ranges.

    mode:
        "max"
        "min"
    """

    count = len(left)

    extreme_values = np.full(
        count,
        np.nan,
        dtype=np.float64,
    )

    extreme_indices = np.full(
        count,
        -1,
        dtype=np.int64,
    )

    valid = (
        (left >= 0)
        & (right >= left)
    )

    if not valid.any():
        return (
            extreme_values,
            extreme_indices,
        )

    positions = np.flatnonzero(
        valid
    )

    lengths = (
        right[positions]
        - left[positions]
        + 1
    )

    powers = np.floor(
        np.log2(lengths)
    ).astype(np.int64)

    for power in np.unique(
        powers
    ):

        mask = (
            powers == power
        )

        current_positions = (
            positions[mask]
        )

        block_size = (
            1 << power
        )

        left_start = (
            left[
                current_positions
            ]
        )

        right_start = (
            right[
                current_positions
            ]
            - block_size
            + 1
        )

        left_values = (
            value_table[
                power
            ][left_start]
        )

        right_values = (
            value_table[
                power
            ][right_start]
        )

        left_indices = (
            index_table[
                power
            ][left_start]
        )

        right_indices = (
            index_table[
                power
            ][right_start]
        )

        if mode == "max":

            choose_left = (
                (left_values > right_values)
                |
                (
                    (left_values == right_values)
                    &
                    (
                        left_indices
                        <= right_indices
                    )
                )
            )

        elif mode == "min":

            choose_left = (
                (left_values < right_values)
                |
                (
                    (left_values == right_values)
                    &
                    (
                        left_indices
                        <= right_indices
                    )
                )
            )

        else:

            raise ValueError(
                "mode must be 'max' or 'min'"
            )

        extreme_values[
            current_positions
        ] = np.where(
            choose_left,
            left_values,
            right_values,
        )

        extreme_indices[
            current_positions
        ] = np.where(
            choose_left,
            left_indices,
            right_indices,
        )

    return (
        extreme_values,
        extreme_indices,
    )


def load_raw(
    symbol: str,
) -> pd.DataFrame:

    input_file = (
        RAW_DIR
        / symbol
        / f"{symbol}_1m.parquet"
    )

    df = pd.read_parquet(
        input_file,
        columns=[
            "open_time",
            "high",
            "low",
        ],
    )

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True,
    )

    df = (
        df
        .sort_values("open_time")
        .drop_duplicates(
            subset=["open_time"]
        )
        .reset_index(drop=True)
    )

    return df


def load_events(
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """
    Load the completed pre-Part-16 first-hit dataset.

    It already contains:
        target_2_5_price
        target_2_5_first_hit_timestamp
        target_2_5_time_minutes
    """

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_first_hit.parquet"
        )
    )

    df = pd.read_parquet(
        input_file
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    df[
        "target_2_5_first_hit_timestamp"
    ] = pd.to_datetime(
        df[
            "target_2_5_first_hit_timestamp"
        ],
        utc=True,
    )

    return df


def calculate_post_activation_behavior(
    symbol: str,
    timeframe: str,
):

    print(
        f"\nProcessing {symbol} {timeframe}"
    )

    events = load_events(
        symbol,
        timeframe,
    )

    raw = load_raw(
        symbol
    )

    original_row_count = len(
        events
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

    print(
        "  Building range lookups..."
    )

    (
        max_value_table,
        max_index_table,
    ) = build_sparse_max_table(
        highs
    )

    (
        min_value_table,
        min_index_table,
    ) = build_sparse_min_table(
        lows
    )

    # ---------------------------------------------------------
    # Multiple classification rows can share the exact same
    # underlying touch and +2.5% activation.
    #
    # Calculate once per unique touch timestamp + price.
    # ---------------------------------------------------------

    unique_events = (
        events[
            [
                "timestamp",
                "price",
                "target_2_5_price",
                "target_2_5_first_hit_timestamp",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    print(
        f"  Event rows: "
        f"{len(events):,}"
    )

    print(
        f"  Unique touch candles/prices: "
        f"{len(unique_events):,}"
    )

    activated = (
        unique_events[
            "target_2_5_first_hit_timestamp"
        ].notna()
    )

    print(
        f"  Reached +2.5%: "
        f"{int(activated.sum()):,}"
    )

    print(
        f"  Did not reach +2.5%: "
        f"{int((~activated).sum()):,}"
    )

    unique_events[
        "trailing_activation_reached"
    ] = activated

    unique_events[
        "trailing_activation_timestamp"
    ] = unique_events[
        "target_2_5_first_hit_timestamp"
    ]

    unique_events[
        "trailing_activation_price"
    ] = unique_events[
        "target_2_5_price"
    ]

    # ---------------------------------------------------------
    # IMPORTANT:
    #
    # +2.5% is first observed inside the activation 1m candle.
    # We do not know the exact intraminute sequence after the hit.
    #
    # Therefore post-activation research starts at the NEXT
    # raw 1-minute candle.
    # ---------------------------------------------------------

    post_activation_start = pd.Series(
        pd.NaT,
        index=unique_events.index,
        dtype="datetime64[us, UTC]",
    )

    post_activation_start.loc[
        activated
    ] = (
        unique_events.loc[
            activated,
            "target_2_5_first_hit_timestamp",
        ]
        + pd.Timedelta("1min")
    )

    unique_events[
        "post_activation_start_timestamp"
    ] = post_activation_start

    start_indices = np.full(
        len(unique_events),
        -1,
        dtype=np.int64,
    )

    activated_positions = np.flatnonzero(
        activated.to_numpy()
    )

    if len(
        activated_positions
    ) > 0:

        start_indices[
            activated_positions
        ] = raw_times.get_indexer(
            post_activation_start.iloc[
                activated_positions
            ]
        )

    activation_prices = (
        unique_events[
            "trailing_activation_price"
        ]
        .to_numpy(
            dtype=np.float64
        )
    )

    # ---------------------------------------------------------
    # Calculate peak and post-peak retracement for each window.
    # ---------------------------------------------------------

    for (
        window_name,
        window_minutes,
    ) in WINDOWS.items():

        print(
            f"  Checking post-activation {window_name}"
        )

        requested_end_indices = (
            start_indices
            + window_minutes
            - 1
        )

        window_complete = (
            activated.to_numpy()
            & (start_indices >= 0)
            & (
                requested_end_indices
                < len(raw)
            )
        )

        complete_column = (
            f"post_activation_window_complete_{window_name}"
        )

        unique_events[
            complete_column
        ] = pd.array(
            [
                pd.NA
            ] * len(unique_events),
            dtype="boolean",
        )

        unique_events.loc[
            activated,
            complete_column,
        ] = False

        unique_events.loc[
            window_complete,
            complete_column,
        ] = True

        # -----------------------------------------------------
        # Peak after +2.5% activation
        # -----------------------------------------------------

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

        query_left = np.full(
            len(unique_events),
            -1,
            dtype=np.int64,
        )

        query_right = np.full(
            len(unique_events),
            -1,
            dtype=np.int64,
        )

        query_left[
            window_complete
        ] = start_indices[
            window_complete
        ]

        query_right[
            window_complete
        ] = requested_end_indices[
            window_complete
        ]

        (
            peak_prices,
            peak_indices,
        ) = range_extreme_with_index(
            value_table=max_value_table,
            index_table=max_index_table,
            left=query_left,
            right=query_right,
            mode="max",
        )

        unique_events[
            peak_price_column
        ] = peak_prices

        extra_upside = (
            (
                peak_prices
                - activation_prices
            )
            / activation_prices
            * 100
        )

        unique_events[
            extra_upside_column
        ] = extra_upside

        peak_timestamps = pd.Series(
            pd.NaT,
            index=unique_events.index,
            dtype="datetime64[us, UTC]",
        )

        complete_positions = np.flatnonzero(
            window_complete
        )

        if len(
            complete_positions
        ) > 0:

            peak_timestamps.iloc[
                complete_positions
            ] = raw_times[
                peak_indices[
                    complete_positions
                ]
            ]

        unique_events[
            peak_timestamp_column
        ] = peak_timestamps

        time_to_peak = np.full(
            len(unique_events),
            np.nan,
            dtype=np.float64,
        )

        if len(
            complete_positions
        ) > 0:

            time_to_peak[
                complete_positions
            ] = (
                peak_indices[
                    complete_positions
                ]
                - start_indices[
                    complete_positions
                ]
                + 1
            )

        unique_events[
            peak_time_column
        ] = time_to_peak

        # -----------------------------------------------------
        # Retracement AFTER the peak.
        #
        # We start from the NEXT 1-minute candle after the peak
        # to avoid assuming intraminute ordering within the peak
        # candle itself.
        #
        # The retracement search ends at the same fixed
        # activation-window end.
        # -----------------------------------------------------

        retracement_available = (
            window_complete
            & (
                peak_indices
                < requested_end_indices
            )
        )

        retracement_available_column = (
            f"post_peak_retracement_available_{window_name}"
        )

        unique_events[
            retracement_available_column
        ] = pd.array(
            [
                pd.NA
            ] * len(unique_events),
            dtype="boolean",
        )

        unique_events.loc[
            activated,
            retracement_available_column,
        ] = False

        unique_events.loc[
            retracement_available,
            retracement_available_column,
        ] = True

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

        retracement_left = np.full(
            len(unique_events),
            -1,
            dtype=np.int64,
        )

        retracement_right = np.full(
            len(unique_events),
            -1,
            dtype=np.int64,
        )

        retracement_left[
            retracement_available
        ] = (
            peak_indices[
                retracement_available
            ]
            + 1
        )

        retracement_right[
            retracement_available
        ] = requested_end_indices[
            retracement_available
        ]

        (
            lowest_after_peak,
            lowest_after_peak_indices,
        ) = range_extreme_with_index(
            value_table=min_value_table,
            index_table=min_index_table,
            left=retracement_left,
            right=retracement_right,
            mode="min",
        )

        unique_events[
            lowest_after_peak_column
        ] = lowest_after_peak

        retracement_pct = (
            (
                lowest_after_peak
                - peak_prices
            )
            / peak_prices
            * 100
        )

        unique_events[
            retracement_column
        ] = retracement_pct

        retracement_timestamps = pd.Series(
            pd.NaT,
            index=unique_events.index,
            dtype="datetime64[us, UTC]",
        )

        retracement_positions = np.flatnonzero(
            retracement_available
        )

        if len(
            retracement_positions
        ) > 0:

            retracement_timestamps.iloc[
                retracement_positions
            ] = raw_times[
                lowest_after_peak_indices[
                    retracement_positions
                ]
            ]

        unique_events[
            retracement_timestamp_column
        ] = retracement_timestamps

        time_from_peak = np.full(
            len(unique_events),
            np.nan,
            dtype=np.float64,
        )

        if len(
            retracement_positions
        ) > 0:

            time_from_peak[
                retracement_positions
            ] = (
                lowest_after_peak_indices[
                    retracement_positions
                ]
                - peak_indices[
                    retracement_positions
                ]
            )

        unique_events[
            retracement_time_column
        ] = time_from_peak

        # -----------------------------------------------------
        # Diagnostics
        # -----------------------------------------------------

        complete_count = int(
            window_complete.sum()
        )

        incomplete_count = int(
            activated.sum()
            - complete_count
        )

        retracement_count = int(
            retracement_available.sum()
        )

        print(
            f"    complete activated windows: "
            f"{complete_count:,}"
        )

        print(
            f"    incomplete activated windows: "
            f"{incomplete_count:,}"
        )

        print(
            f"    retracement measurable: "
            f"{retracement_count:,}"
        )

        valid_extra_upside = (
            unique_events.loc[
                window_complete,
                extra_upside_column,
            ]
            .dropna()
        )

        valid_retracement = (
            unique_events.loc[
                retracement_available,
                retracement_column,
            ]
            .dropna()
        )

        if len(
            valid_extra_upside
        ) > 0:

            print(
                f"    median extra upside: "
                f"{valid_extra_upside.median():.4f}%"
            )

        if len(
            valid_retracement
        ) > 0:

            print(
                f"    median retracement: "
                f"{valid_retracement.median():.4f}%"
            )

    # ---------------------------------------------------------
    # Merge research results back to every classified event row.
    # ---------------------------------------------------------

    new_columns = [
        column
        for column
        in unique_events.columns
        if column not in [
            "timestamp",
            "price",
            "target_2_5_price",
            "target_2_5_first_hit_timestamp",
        ]
    ]

    output = events.merge(
        unique_events[
            [
                "timestamp",
                "price",
                "target_2_5_price",
                "target_2_5_first_hit_timestamp",
                *new_columns,
            ]
        ],
        on=[
            "timestamp",
            "price",
            "target_2_5_price",
            "target_2_5_first_hit_timestamp",
        ],
        how="left",
        validate="many_to_one",
    )

    if len(output) != original_row_count:

        raise ValueError(
            f"{symbol} {timeframe}: "
            f"row count changed from "
            f"{original_row_count:,} "
            f"to {len(output):,}"
        )

    output = (
        output
        .sort_values(
            [
                "timestamp",
                "average_type",
                "touch_zone",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    output_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_post_activation.parquet"
        )
    )

    output.to_parquet(
        output_file,
        index=False,
    )

    print(
        f"Saved: {output_file}"
    )

    print(
        f"Rows: {len(output):,}"
    )


def main():

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            calculate_post_activation_behavior(
                symbol,
                timeframe,
            )


if __name__ == "__main__":
    main()
