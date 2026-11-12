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

    Store:
    - maximum value
    - earliest index where that maximum occurred
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


def range_max_with_index(
    value_table,
    index_table,
    left: np.ndarray,
    right: np.ndarray,
):
    """
    Return maximum value and earliest index
    for inclusive ranges [left, right].
    """

    count = len(left)

    maximum_values = np.full(
        count,
        np.nan,
        dtype=np.float64,
    )

    maximum_indices = np.full(
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
            maximum_values,
            maximum_indices,
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

        maximum_values[
            current_positions
        ] = np.where(
            choose_left,
            left_values,
            right_values,
        )

        maximum_indices[
            current_positions
        ] = np.where(
            choose_left,
            left_indices,
            right_indices,
        )

    return (
        maximum_values,
        maximum_indices,
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
    Use Part 14 output so all previous research columns
    remain preserved.
    """

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_max_downside.parquet"
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


def calculate_maximum_upside(
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

    highs = raw[
        "high"
    ].to_numpy(
        dtype=np.float64
    )

    print(
        "  Building range-max lookup..."
    )

    (
        value_table,
        index_table,
    ) = build_sparse_max_table(
        highs
    )

    # ---------------------------------------------------------
    # Calculate once per unique touch candle / touch price
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
    # Observation begins AFTER touch candle completes.
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
        "upside_observation_start_timestamp"
    ] = observation_start

    prices = (
        unique_events[
            "price"
        ]
        .to_numpy(
            dtype=np.float64
        )
    )

    # ---------------------------------------------------------
    # Calculate each window
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
            f"upside_window_complete_{window_name}"
        )

        unique_events[
            complete_column
        ] = window_complete

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

        # -----------------------------------------------------
        # Only complete windows are measured.
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
            highest_prices,
            highest_indices,
        ) = range_max_with_index(
            value_table=value_table,
            index_table=index_table,
            left=query_left,
            right=query_right,
        )

        unique_events[
            highest_price_column
        ] = highest_prices

        # -----------------------------------------------------
        # MFE / maximum upside percentage
        #
        # touch price = 100
        # highest future high = 103
        #
        # upside = +3%
        # -----------------------------------------------------

        maximum_upside = (
            (
                highest_prices
                - prices
            )
            / prices
            * 100
        )

        unique_events[
            upside_column
        ] = maximum_upside

        # -----------------------------------------------------
        # Timestamp where maximum upside first occurred
        # -----------------------------------------------------

        maximum_timestamps = pd.Series(
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

            maximum_timestamps.iloc[
                complete_positions
            ] = raw_times[
                highest_indices[
                    complete_positions
                ]
            ]

        unique_events[
            timestamp_column
        ] = maximum_timestamps

        # -----------------------------------------------------
        # Time to maximum upside.
        #
        # First future candle = minute 1.
        # -----------------------------------------------------

        time_to_maximum = np.full(
            len(unique_events),
            np.nan,
            dtype=np.float64,
        )

        if len(
            complete_positions
        ) > 0:

            time_to_maximum[
                complete_positions
            ] = (
                highest_indices[
                    complete_positions
                ]
                - start_indices[
                    complete_positions
                ]
                + 1
            )

        unique_events[
            time_column
        ] = time_to_maximum

        valid_count = int(
            window_complete.sum()
        )

        incomplete_count = (
            len(unique_events)
            - valid_count
        )

        valid_upside = (
            unique_events.loc[
                window_complete,
                upside_column,
            ]
        )

        print(
            f"    complete: "
            f"{valid_count:,} | "
            f"incomplete: "
            f"{incomplete_count:,}"
        )

        if len(valid_upside) > 0:

            print(
                f"    median upside: "
                f"{valid_upside.median():.4f}%"
            )

    # ---------------------------------------------------------
    # Merge results back to all classified event rows
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
            f"_touch_events_with_max_upside.parquet"
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

            calculate_maximum_upside(
                symbol,
                timeframe,
            )


if __name__ == "__main__":
    main()