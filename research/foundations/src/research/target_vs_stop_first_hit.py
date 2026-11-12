from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")

TARGET_PCT = 0.025

STOP_LEVELS = {
    "1_0": 0.010,
    "1_5": 0.015,
    "2_0": 0.020,
    "2_5": 0.025,
    "3_0": 0.030,
}

OBSERVATION_MINUTES = 24 * 60


def build_sparse_max_table(values: np.ndarray):
    """Build a sparse table for fast range-maximum queries."""
    n = len(values)
    max_power = int(np.floor(np.log2(n)))
    table = [values.astype(np.float64)]

    for power in range(1, max_power + 1):
        previous = table[power - 1]
        half = 1 << (power - 1)
        length = n - (1 << power) + 1

        current = np.maximum(
            previous[:length],
            previous[half:half + length],
        )
        table.append(current)

    return table


def range_max(sparse_table, left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Inclusive range maximum for many [left, right] ranges."""
    result = np.full(len(left), np.nan, dtype=np.float64)

    valid = (left >= 0) & (right >= left)
    if not valid.any():
        return result

    positions = np.flatnonzero(valid)
    lengths = right[positions] - left[positions] + 1
    powers = np.floor(np.log2(lengths)).astype(np.int64)

    for power in np.unique(powers):
        mask = powers == power
        current_positions = positions[mask]
        block_size = 1 << power

        left_start = left[current_positions]
        right_start = right[current_positions] - block_size + 1

        left_values = sparse_table[power][left_start]
        right_values = sparse_table[power][right_start]

        result[current_positions] = np.maximum(left_values, right_values)

    return result


def find_first_threshold_hit(
    sparse_table,
    start_indices: np.ndarray,
    end_indices: np.ndarray,
    thresholds: np.ndarray,
):
    """
    Find the first index where the queried series reaches or exceeds
    the threshold.

    Used for:
      - target: raw high >= target price
      - stop:   -raw low >= -stop price
    """
    count = len(start_indices)
    hit_exists = np.zeros(count, dtype=bool)
    first_hit_index = np.full(count, -1, dtype=np.int64)

    valid = (start_indices >= 0) & (end_indices >= start_indices)
    if not valid.any():
        return hit_exists, first_hit_index

    valid_positions = np.flatnonzero(valid)
    left = start_indices[valid_positions]
    right = end_indices[valid_positions]
    target = thresholds[valid_positions]

    maximum = range_max(sparse_table, left, right)
    can_hit = maximum >= target

    hit_positions = valid_positions[can_hit]
    hit_exists[hit_positions] = True

    if len(hit_positions) == 0:
        return hit_exists, first_hit_index

    search_left = start_indices[hit_positions].copy()
    search_right = end_indices[hit_positions].copy()
    target = thresholds[hit_positions]

    while np.any(search_left < search_right):
        active = search_left < search_right
        mid = (search_left[active] + search_right[active]) // 2

        prefix_max = range_max(
            sparse_table,
            start_indices[hit_positions[active]],
            mid,
        )

        hit_by_mid = prefix_max >= target[active]
        active_positions = np.flatnonzero(active)

        move_right = active_positions[hit_by_mid]
        move_left = active_positions[~hit_by_mid]

        search_right[move_right] = mid[hit_by_mid]
        search_left[move_left] = mid[~hit_by_mid] + 1

    first_hit_index[hit_positions] = search_left
    return hit_exists, first_hit_index


def load_raw(symbol: str) -> pd.DataFrame:
    input_file = RAW_DIR / symbol / f"{symbol}_1m.parquet"

    df = pd.read_parquet(
        input_file,
        columns=["open_time", "high", "low"],
    )

    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)

    return (
        df.sort_values("open_time")
        .drop_duplicates(subset=["open_time"])
        .reset_index(drop=True)
    )


def load_events(symbol: str, timeframe: str) -> pd.DataFrame:
    input_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_max_upside.parquet"
    )

    df = pd.read_parquet(input_file)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def calculate_first_hit(symbol: str, timeframe: str):
    """
    Compare a +2.5% target against several downside stop levels.

    Possible outcomes:
      target_first
      stop_first
      same_candle_ambiguous
      neither
      incomplete_unknown

    If target and stop are first reached in the same raw 1-minute candle,
    OHLC data cannot tell us which occurred first inside that minute, so
    the result is marked ambiguous.
    """
    print(f"\nProcessing {symbol} {timeframe}")

    events = load_events(symbol, timeframe)
    raw = load_raw(symbol)
    original_row_count = len(events)

    raw_times = pd.DatetimeIndex(raw["open_time"])
    highs = raw["high"].to_numpy(dtype=np.float64)
    lows = raw["low"].to_numpy(dtype=np.float64)

    print("  Building range lookups...")
    high_sparse = build_sparse_max_table(highs)
    negative_low_sparse = build_sparse_max_table(-lows)

    unique_events = (
        events[["timestamp", "price"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    print(f"  Event rows: {len(events):,}")
    print(f"  Unique touch candles/prices: {len(unique_events):,}")

    timeframe_delta = pd.Timedelta(timeframe)
    observation_start = unique_events["timestamp"] + timeframe_delta
    start_indices = raw_times.get_indexer(observation_start)

    requested_end_indices = start_indices + OBSERVATION_MINUTES - 1

    observation_complete = (
        (start_indices >= 0)
        & (requested_end_indices < len(raw))
    )

    actual_end_indices = np.minimum(requested_end_indices, len(raw) - 1)
    actual_end_indices[start_indices < 0] = -1

    unique_events["first_hit_observation_start_timestamp"] = observation_start
    unique_events["first_hit_window_complete_24h"] = observation_complete

    prices = unique_events["price"].to_numpy(dtype=np.float64)

    # +2.5% target
    target_prices = prices * (1 + TARGET_PCT)

    target_hit, target_hit_indices = find_first_threshold_hit(
        sparse_table=high_sparse,
        start_indices=start_indices,
        end_indices=actual_end_indices,
        thresholds=target_prices,
    )

    unique_events["target_2_5_price"] = target_prices

    target_hit_timestamps = pd.Series(
        pd.NaT,
        index=unique_events.index,
        dtype="datetime64[us, UTC]",
    )

    target_hit_minutes = np.full(len(unique_events), np.nan, dtype=np.float64)
    target_positions = np.flatnonzero(target_hit)

    if len(target_positions) > 0:
        target_hit_timestamps.iloc[target_positions] = raw_times[
            target_hit_indices[target_positions]
        ]
        target_hit_minutes[target_positions] = (
            target_hit_indices[target_positions]
            - start_indices[target_positions]
            + 1
        )

    unique_events["target_2_5_first_hit_timestamp"] = target_hit_timestamps
    unique_events["target_2_5_time_minutes"] = target_hit_minutes

    for stop_name, stop_pct in STOP_LEVELS.items():
        print(f"  Comparing +2.5% vs -{stop_pct * 100:g}%")

        stop_prices = prices * (1 - stop_pct)

        stop_hit, stop_hit_indices = find_first_threshold_hit(
            sparse_table=negative_low_sparse,
            start_indices=start_indices,
            end_indices=actual_end_indices,
            thresholds=-stop_prices,
        )

        stop_price_column = f"stop_{stop_name}_price"
        stop_timestamp_column = f"stop_{stop_name}_first_hit_timestamp"
        stop_time_column = f"stop_{stop_name}_time_minutes"
        outcome_column = f"target_2_5_vs_stop_{stop_name}_outcome"

        unique_events[stop_price_column] = stop_prices

        stop_hit_timestamps = pd.Series(
            pd.NaT,
            index=unique_events.index,
            dtype="datetime64[us, UTC]",
        )

        stop_hit_minutes = np.full(len(unique_events), np.nan, dtype=np.float64)
        stop_positions = np.flatnonzero(stop_hit)

        if len(stop_positions) > 0:
            stop_hit_timestamps.iloc[stop_positions] = raw_times[
                stop_hit_indices[stop_positions]
            ]
            stop_hit_minutes[stop_positions] = (
                stop_hit_indices[stop_positions]
                - start_indices[stop_positions]
                + 1
            )

        unique_events[stop_timestamp_column] = stop_hit_timestamps
        unique_events[stop_time_column] = stop_hit_minutes

        outcome = np.full(
            len(unique_events),
            "incomplete_unknown",
            dtype=object,
        )

        both_hit = target_hit & stop_hit
        target_only = target_hit & ~stop_hit
        stop_only = stop_hit & ~target_hit
        neither = ~target_hit & ~stop_hit

        target_first = both_hit & (target_hit_indices < stop_hit_indices)
        stop_first = both_hit & (stop_hit_indices < target_hit_indices)
        same_candle = both_hit & (target_hit_indices == stop_hit_indices)

        outcome[target_first] = "target_first"
        outcome[stop_first] = "stop_first"
        outcome[same_candle] = "same_candle_ambiguous"

        # If only one side has been observed, the ordering is already known,
        # even if the full 24h window is incomplete.
        outcome[target_only] = "target_first"
        outcome[stop_only] = "stop_first"

        # Neither is only confirmed when the full 24h window exists.
        outcome[neither & observation_complete] = "neither"

        unique_events[outcome_column] = outcome

        counts = pd.Series(outcome).value_counts()

        print(f"    target first: {int(counts.get('target_first', 0)):,}")
        print(f"    stop first: {int(counts.get('stop_first', 0)):,}")
        print(
            "    same candle ambiguous: "
            f"{int(counts.get('same_candle_ambiguous', 0)):,}"
        )
        print(f"    neither: {int(counts.get('neither', 0)):,}")
        print(
            "    incomplete unknown: "
            f"{int(counts.get('incomplete_unknown', 0)):,}"
        )

    new_columns = [
        column
        for column in unique_events.columns
        if column not in ["timestamp", "price"]
    ]

    output = events.merge(
        unique_events[["timestamp", "price", *new_columns]],
        on=["timestamp", "price"],
        how="left",
        validate="many_to_one",
    )

    if len(output) != original_row_count:
        raise ValueError(
            f"{symbol} {timeframe}: row count changed from "
            f"{original_row_count:,} to {len(output):,}"
        )

    output = (
        output.sort_values(["timestamp", "average_type", "touch_zone"])
        .reset_index(drop=True)
    )

    output_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_first_hit.parquet"
    )

    output.to_parquet(output_file, index=False)

    print(f"Saved: {output_file}")
    print(f"Rows: {len(output):,}")


def main():
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            calculate_first_hit(symbol, timeframe)


if __name__ == "__main__":
    main()