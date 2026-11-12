from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")


HORIZONS = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "24h": "24h",
}


def load_raw_1m(symbol: str) -> pd.DataFrame:
    """
    Load validated raw 1-minute candles.

    We use open_time for future-price matching instead of close_time
    because Binance historical files use different close_time precision
    across different parts of the dataset.
    """

    input_file = (
        RAW_DIR
        / symbol
        / f"{symbol}_1m.parquet"
    )

    df = pd.read_parquet(
        input_file,
        columns=[
            "open_time",
            "close",
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


def load_touch_events(
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    """
    Load Part 11 touch-event dataset.
    """

    input_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events.parquet"
    )

    df = pd.read_parquet(input_file)

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    return df


def calculate_forward_returns(
    symbol: str,
    timeframe: str,
):
    """
    Calculate future prices and forward returns.

    Part 11 timestamp represents the touch candle open_time.

    For each horizon:

        target_open_time = touch timestamp + horizon

    We find that exact candle in the validated raw 1m dataset
    and use its close as the future price.

    No nearest matching.
    No interpolation.
    """

    print(f"\nProcessing {symbol} {timeframe}")

    events = load_touch_events(
        symbol,
        timeframe,
    )

    raw = load_raw_1m(symbol)

    original_row_count = len(events)

    # ---------------------------------------------------------
    # Prepare exact future-price lookup
    # ---------------------------------------------------------

    future_lookup = raw.rename(
        columns={
            "open_time": "target_timestamp",
            "close": "future_close",
        }
    )

    # ---------------------------------------------------------
    # Calculate forward returns
    # ---------------------------------------------------------

    for horizon_name, horizon_delta in HORIZONS.items():

        target_column = (
            f"_target_timestamp_{horizon_name}"
        )

        events[target_column] = (
            events["timestamp"]
            + pd.Timedelta(horizon_delta)
        )

        lookup = future_lookup.rename(
            columns={
                "target_timestamp": target_column,
            }
        )

        events = events.merge(
            lookup,
            on=target_column,
            how="left",
            validate="many_to_one",
        )

        future_price_column = (
            f"future_price_{horizon_name}"
        )

        return_column = (
            f"return_{horizon_name}_pct"
        )

        events[future_price_column] = (
            events["future_close"]
        )

        events[return_column] = (
            (
                events[future_price_column]
                - events["price"]
            )
            / events["price"]
            * 100
        )

        available = (
            events[future_price_column]
            .notna()
            .sum()
        )

        missing = (
            events[future_price_column]
            .isna()
            .sum()
        )

        print(
            f"  {horizon_name}: "
            f"{available:,} available, "
            f"{missing:,} missing"
        )

        # Remove temporary columns
        events = events.drop(
            columns=[
                target_column,
                "future_close",
            ]
        )

        # Protect against accidental row multiplication
        if len(events) != original_row_count:
            raise ValueError(
                f"{symbol} {timeframe} {horizon_name}: "
                f"row count changed from "
                f"{original_row_count:,} "
                f"to {len(events):,}"
            )

    # ---------------------------------------------------------
    # Restore deterministic event order
    # ---------------------------------------------------------

    events = events.sort_values(
        [
            "timestamp",
            "average_type",
            "touch_zone",
        ]
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    output_dir = (
        RESEARCH_DIR
        / symbol
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / f"{symbol}_{timeframe}_touch_events_with_returns.parquet"
    )

    events.to_parquet(
        output_file,
        index=False,
    )

    print(f"Saved: {output_file}")
    print(f"Rows: {len(events):,}")


def main():

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            calculate_forward_returns(
                symbol,
                timeframe,
            )


if __name__ == "__main__":
    main()