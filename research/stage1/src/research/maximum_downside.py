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


def build_sparse_min_table(values: np.ndarray):
    """
    Build sparse tables for fast range-minimum queries.

    We store both:
    - minimum value
    - index where that minimum first occurred

    If the same minimum occurs more than once,
    the earliest occurrence is kept.
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


def range_min_with_index(
    value_table,
    index_table,
    left: np.ndarray,
    right: np.ndarray,
):
    """
    Return minimum value and earliest index
    for inclusive ranges [left, right].
    """

    count = len(left)

    minimum_values = np.full(
        count,
        np.nan,
        dtype=np.float64,
    )

    minimum_indices = np.full(
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
            minimum_values,
            minimum_indices,
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

        minimum_values[
            current_positions
        ] = np.where(
            choose_left,
            left_values,
            right_values,
        )

        minimum_indices[
            current_positions
        ] = np.where(
            choose_left,
            left_indices,
            right_indices,
        )

    return (
        minimum_values,
        minimum_indices,
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
    Use the completed Part 13 dataset as input,
    preserving all previous research columns.
    """

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_profit_reach.parquet"
        )
    )

    df = pd.read_parquet(
        input_file
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    return df


def calculate_maximum_downside(
    symbol: str,
    timeframe: str,
):

    print(
        f"\nProcessing "
        f"{symbol} {timeframe}"
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

    lows = raw[
        "low"
    ].to_numpy(
        dtype=np.float64
    )

    print(
        "  Building range-min lookup..."
    )

    (
        value_table,
        index_table,
    ) = build_sparse_min_table(
        lows
    )

    # ---------------------------------------------------------
    # Same touch candle can appear multiple times because of:
    #
    # average type
    # touch zone
    #
    # Downside depends only on:
    # timestamp + price + timeframe
    #
    # Therefore calculate once per unique touch candle/price.
    # ---------------------------------------------------------

    unique_events = (
        events[
            [
                "timestamp",
                "price",
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

    # ---------------------------------------------------------
    # Observation begins after touch candle completes.
    #
    # 1m touch 09:05 -> first future candle 09:06
    # 3m touch 09:03 -> first future candle 09:06
    # 5m touch 09:05 -> first future candle 09:10
    # ---------------------------------------------------------

    timeframe_delta = pd.Timedelta(
        timeframe
    )

    observation_start = (
        unique_events[
            "timestamp"
        ]
        + timeframe_delta
    )

    start_indices = (
        raw_times.get_indexer(
            observation_start
        )
    )

    unique_events[
        "downside_observation_start_timestamp"
    ] = observation_start

    # ---------------------------------------------------------
    # Calculate each downside window
    # ---------------------------------------------------------

    for (
        window_name,
        window_minutes,
    ) in WINDOWS.items():

        print(
            f"  Checking {window_name}"
        )

        requested_end_indices = (
            start_indices
            + window_minutes
            - 1
        )

        window_complete = (
            (start_indices >= 0)
            &
            (
                requested_end_indices
                < len(raw)
            )
        )

        complete_column = (
            f"downside_window_complete_{window_name}"
        )

        unique_events[
            complete_column
        ] = window_complete

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

        # -----------------------------------------------------
        # Query only complete windows.
        #
        # Incomplete windows stay NA because their true future
        # minimum is unknown.
        # -----------------------------------------------------

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
            lowest_prices,
            lowest_indices,
        ) = range_min_with_index(
            value_table=value_table,
            index_table=index_table,
            left=query_left,
            right=query_right,
        )

        unique_events[
            lowest_price_column
        ] = lowest_prices

        # -----------------------------------------------------
        # MAE / maximum downside percentage
        #
        # Example:
        #
        # touch price = 100
        # lowest future low = 98
        #
        # downside = -2%
        # -----------------------------------------------------

        prices = (
            unique_events[
                "price"
            ]
            .to_numpy(
                dtype=np.float64
            )
        )

        maximum_downside = (
            (
                lowest_prices
                - prices
            )
            / prices
            * 100
        )

        unique_events[
            downside_column
        ] = maximum_downside

        # -----------------------------------------------------
        # Timestamp where worst downside first occurred
        # -----------------------------------------------------

        minimum_timestamps = pd.Series(
            pd.NaT,
            index=unique_events.index,
            dtype="datetime64[us, UTC]",
        )

        complete_positions = (
            np.flatnonzero(
                window_complete
            )
        )

        if len(
            complete_positions
        ) > 0:

            minimum_timestamps.iloc[
                complete_positions
            ] = raw_times[
                lowest_indices[
                    complete_positions
                ]
            ]

        unique_events[
            timestamp_column
        ] = minimum_timestamps

        # -----------------------------------------------------
        # Time to worst downside.
        #
        # First future candle = minute 1.
        # -----------------------------------------------------

        time_to_minimum = np.full(
            len(unique_events),
            np.nan,
            dtype=np.float64,
        )

        if len(
            complete_positions
        ) > 0:

            time_to_minimum[
                complete_positions
            ] = (
                lowest_indices[
                    complete_positions
                ]
                - start_indices[
                    complete_positions
                ]
                + 1
            )

        unique_events[
            time_column
        ] = time_to_minimum

        valid_count = int(
            window_complete.sum()
        )

        incomplete_count = (
            len(unique_events)
            - valid_count
        )

        valid_downside = (
            unique_events.loc[
                window_complete,
                downside_column,
            ]
        )

        print(
            f"    complete: "
            f"{valid_count:,} | "
            f"incomplete: "
            f"{incomplete_count:,}"
        )

        if len(valid_downside) > 0:

            print(
                f"    median downside: "
                f"{valid_downside.median():.4f}%"
            )

    # ---------------------------------------------------------
    # Merge calculations back to every classified event row.
    # ---------------------------------------------------------

    new_columns = [
        column
        for column
        in unique_events.columns
        if column not in [
            "timestamp",
            "price",
        ]
    ]

    output = events.merge(
        unique_events[
            [
                "timestamp",
                "price",
                *new_columns,
            ]
        ],
        on=[
            "timestamp",
            "price",
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
            f"_touch_events_with_max_downside.parquet"
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

            calculate_maximum_downside(
                symbol,
                timeframe,
            )


if __name__ == "__main__":
    main()