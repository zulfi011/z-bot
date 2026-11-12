from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")


PROFIT_LEVELS = {
    "0_5": 0.005,
    "1_0": 0.010,
    "1_5": 0.015,
    "2_0": 0.020,
    "2_5": 0.025,
    "3_0": 0.030,
    "5_0": 0.050,
}

OBSERVATION_MINUTES = 24 * 60


def build_sparse_max_table(values: np.ndarray):
    """
    Build a sparse table for fast range-maximum queries.

    This lets us search millions of touch events without scanning
    all 1,440 future candles separately for every event.
    """

    n = len(values)

    max_power = int(np.floor(np.log2(n)))

    table = [values.astype(np.float64)]

    power = 1

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
) -> np.ndarray:
    """
    Return maximum value in inclusive ranges [left, right].

    left and right are arrays, so many range queries are processed
    simultaneously.
    """

    lengths = right - left + 1

    powers = np.floor(
        np.log2(lengths)
    ).astype(np.int64)

    results = np.empty(
        len(left),
        dtype=np.float64,
    )

    for power in np.unique(powers):

        mask = powers == power

        block_size = 1 << power

        left_values = sparse_table[power][
            left[mask]
        ]

        right_start = (
            right[mask]
            - block_size
            + 1
        )

        right_values = sparse_table[power][
            right_start
        ]

        results[mask] = np.maximum(
            left_values,
            right_values,
        )

    return results


def find_first_hits(
    sparse_table,
    highs: np.ndarray,
    start_indices: np.ndarray,
    end_indices: np.ndarray,
    thresholds: np.ndarray,
):
    """
    Find the first raw 1-minute candle whose high is greater than
    or equal to the requested target price.

    Search range is inclusive:
        start_indices ... end_indices

    Returns:
        reached
        first_hit_indices
    """

    count = len(start_indices)

    reached = np.zeros(
        count,
        dtype=bool,
    )

    first_hit_indices = np.full(
        count,
        -1,
        dtype=np.int64,
    )

    valid = (
        (start_indices >= 0)
        & (end_indices >= start_indices)
        & (start_indices < len(highs))
    )

    if not valid.any():
        return reached, first_hit_indices

    valid_positions = np.flatnonzero(valid)

    left = start_indices[valid_positions]
    right = end_indices[valid_positions]
    target = thresholds[valid_positions]

    maximum = range_max(
        sparse_table,
        left,
        right,
    )

    can_reach = maximum >= target

    reached_positions = valid_positions[
        can_reach
    ]

    reached[reached_positions] = True

    if len(reached_positions) == 0:
        return reached, first_hit_indices

    search_left = start_indices[
        reached_positions
    ].copy()

    search_right = end_indices[
        reached_positions
    ].copy()

    target = thresholds[
        reached_positions
    ]

    # ---------------------------------------------------------
    # Parallel binary search for the first candle whose
    # cumulative range maximum reaches the threshold.
    # ---------------------------------------------------------

    while np.any(search_left < search_right):

        active = search_left < search_right

        mid = (
            search_left[active]
            + search_right[active]
        ) // 2

        prefix_max = range_max(
            sparse_table,
            start_indices[
                reached_positions[active]
            ],
            mid,
        )

        hit_by_mid = (
            prefix_max
            >= target[active]
        )

        active_positions = np.flatnonzero(
            active
        )

        right_positions = active_positions[
            hit_by_mid
        ]

        left_positions = active_positions[
            ~hit_by_mid
        ]

        search_right[right_positions] = (
            mid[hit_by_mid]
        )

        search_left[left_positions] = (
            mid[~hit_by_mid] + 1
        )

    first_hit_indices[
        reached_positions
    ] = search_left

    return reached, first_hit_indices


def load_raw(symbol: str) -> pd.DataFrame:

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
        df.sort_values("open_time")
        .drop_duplicates(subset=["open_time"])
        .reset_index(drop=True)
    )

    return df


def load_events(
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_returns.parquet"
        )
    )

    df = pd.read_parquet(input_file)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    return df


def calculate_profit_reach(
    symbol: str,
    timeframe: str,
):

    print(f"\nProcessing {symbol} {timeframe}")

    events = load_events(
        symbol,
        timeframe,
    )

    raw = load_raw(symbol)

    original_row_count = len(events)

    # ---------------------------------------------------------
    # Build raw lookup
    # ---------------------------------------------------------

    raw_times = pd.DatetimeIndex(
        raw["open_time"]
    )

    highs = raw["high"].to_numpy(
        dtype=np.float64
    )

    print("  Building range-max lookup...")

    sparse_table = build_sparse_max_table(
        highs
    )

    # ---------------------------------------------------------
    # Events contain duplicate rows for average/touch-zone
    # classifications.
    #
    # Profit reach depends only on:
    #     touch candle timestamp
    #     timeframe
    #     touch price
    #
    # Therefore calculate it once per unique touch candle/price
    # and merge the result back to every classified event.
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
        f"  Event rows: {len(events):,}"
    )

    print(
        f"  Unique touch candles/prices: "
        f"{len(unique_events):,}"
    )

    # ---------------------------------------------------------
    # Observation begins AFTER the touch candle is complete.
    #
    # Examples:
    #
    # 1m touch at 09:05
    # touch completes at 09:06 boundary
    # first future 1m candle = 09:06
    #
    # 3m touch at 09:03
    # touch completes at 09:06 boundary
    # first future 1m candle = 09:06
    # ---------------------------------------------------------

    timeframe_delta = pd.Timedelta(
        timeframe
    )

    observation_start = (
        unique_events["timestamp"]
        + timeframe_delta
    )

    start_indices = raw_times.get_indexer(
        observation_start
    )

    # ---------------------------------------------------------
    # A complete 24-hour observation contains exactly
    # 1,440 future 1-minute candles.
    #
    # start candle counts as minute 1.
    # ---------------------------------------------------------

    requested_end_indices = (
        start_indices
        + OBSERVATION_MINUTES
        - 1
    )

    observation_complete = (
        (start_indices >= 0)
        & (
            requested_end_indices
            < len(raw)
        )
    )

    actual_end_indices = np.minimum(
        requested_end_indices,
        len(raw) - 1,
    )

    # Invalid starts should remain invalid.
    actual_end_indices[
        start_indices < 0
    ] = -1

    unique_events[
        "observation_complete_24h"
    ] = observation_complete

    unique_events[
        "observation_start_timestamp"
    ] = observation_start

    # ---------------------------------------------------------
    # Calculate each upside level
    # ---------------------------------------------------------

    for level_name, level_pct in PROFIT_LEVELS.items():

        print(
            f"  Checking +{level_pct * 100:g}%"
        )

        target_price_column = (
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

        target_prices = (
            unique_events["price"].to_numpy(
                dtype=np.float64
            )
            * (1 + level_pct)
        )

        unique_events[
            target_price_column
        ] = target_prices

        reached, first_hit_indices = (
            find_first_hits(
                sparse_table=sparse_table,
                highs=highs,
                start_indices=start_indices,
                end_indices=actual_end_indices,
                thresholds=target_prices,
            )
        )

        # -----------------------------------------------------
        # Nullable boolean:
        #
        # True:
        # target definitely reached.
        #
        # False:
        # target not reached AND full 24h was observed.
        #
        # NA:
        # target not reached but dataset ended before full
        # 24-hour observation was available.
        # -----------------------------------------------------

        reached_values = pd.array(
            [pd.NA] * len(unique_events),
            dtype="boolean",
        )

        reached_values[
            observation_complete
        ] = False

        reached_values[
            reached
        ] = True

        unique_events[
            reached_column
        ] = reached_values

        # -----------------------------------------------------
        # First reached timestamp
        # -----------------------------------------------------

        hit_timestamps = pd.Series(
            pd.NaT,
            index=unique_events.index,
            dtype="datetime64[us, UTC]",
        )

        reached_positions = np.flatnonzero(
            reached
        )

        if len(reached_positions) > 0:

            hit_timestamps.iloc[
                reached_positions
            ] = raw_times[
                first_hit_indices[
                    reached_positions
                ]
            ]

        unique_events[
            hit_timestamp_column
        ] = hit_timestamps

        # -----------------------------------------------------
        # Time to target.
        #
        # With 1-minute OHLC data we do not know the exact
        # second inside the candle when the target was hit.
        #
        # Therefore:
        # first future candle = 1 minute
        # second future candle = 2 minutes
        # etc.
        # -----------------------------------------------------

        time_to_hit = np.full(
            len(unique_events),
            np.nan,
            dtype=np.float64,
        )

        if len(reached_positions) > 0:

            time_to_hit[
                reached_positions
            ] = (
                first_hit_indices[
                    reached_positions
                ]
                - start_indices[
                    reached_positions
                ]
                + 1
            )

        unique_events[
            time_column
        ] = time_to_hit

        true_count = int(
            (reached_values == True)
            .fillna(False)
            .sum()
        )

        false_count = int(
            (reached_values == False)
            .fillna(False)
            .sum()
        )

        unknown_count = int(
            reached_values.isna().sum()
        )

        print(
            f"    reached: {true_count:,} | "
            f"not reached: {false_count:,} | "
            f"unknown: {unknown_count:,}"
        )

    # ---------------------------------------------------------
    # Merge calculations back to every Part 12 event row
    # ---------------------------------------------------------

    result_columns = [
        column
        for column in unique_events.columns
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
                *result_columns,
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

    output = output.sort_values(
        [
            "timestamp",
            "average_type",
            "touch_zone",
        ]
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    output_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_profit_reach.parquet"
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

            calculate_profit_reach(
                symbol,
                timeframe,
            )


if __name__ == "__main__":
    main()