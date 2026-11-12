from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def calculate_daily_averages(symbol: str):
    """
    Calculate 7D, 15D and 30D averages using only
    completed daily closing prices.
    """

    input_file = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_available_closes.parquet"
    )

    df = pd.read_parquet(input_file)

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    df = df.sort_values(
        "open_time"
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # Calculate averages from completed daily closes
    # ---------------------------------------------------------

    df["average_7d"] = (
        df["available_daily_close"]
        .rolling(
            window=7,
            min_periods=7
        )
        .mean()
    )

    df["average_15d"] = (
        df["available_daily_close"]
        .rolling(
            window=15,
            min_periods=15
        )
        .mean()
    )

    df["average_30d"] = (
        df["available_daily_close"]
        .rolling(
            window=30,
            min_periods=30
        )
        .mean()
    )

    return df[
        [
            "open_time",
            "average_7d",
            "average_15d",
            "average_30d",
        ]
    ]


def get_timeframe_file(
    symbol: str,
    timeframe: str
):
    """
    Return the correct input file for each timeframe.

    1m data is stored in data/raw.
    3m and 5m data are stored in data/processed.
    """

    if timeframe == "1m":
        return (
            RAW_DIR
            / symbol
            / f"{symbol}_1m.parquet"
        )

    return (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}.parquet"
    )


def attach_to_timeframe(
    symbol: str,
    timeframe: str,
    daily_averages: pd.DataFrame,
):
    """
    Attach the latest available daily averages
    to each small-timeframe candle.

    merge_asof(direction='backward') ensures that
    a candle only receives information that was
    already available at that timestamp.
    """

    input_file = get_timeframe_file(
        symbol,
        timeframe
    )

    output_file = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_averages.parquet"
    )

    print(
        f"\nReading {timeframe} data..."
    )

    candles = pd.read_parquet(
        input_file
    )

    candles["open_time"] = pd.to_datetime(
        candles["open_time"],
        utc=True
    )

    candles = candles.sort_values(
        "open_time"
    ).reset_index(drop=True)

    daily_averages = (
        daily_averages
        .sort_values("open_time")
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # Attach the latest known averages.
    #
    # backward = use the most recent daily average
    # whose timestamp is <= the candle timestamp.
    # ---------------------------------------------------------

    candles = pd.merge_asof(
        candles,
        daily_averages,
        on="open_time",
        direction="backward",
    )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    candles.to_parquet(
        output_file,
        index=False
    )

    print(
        f"Saved: {output_file}"
    )

    print(
        f"Rows: {len(candles):,}"
    )

    print(
        f"7D average available: "
        f"{candles['average_7d'].notna().sum():,}"
    )

    print(
        f"15D average available: "
        f"{candles['average_15d'].notna().sum():,}"
    )

    print(
        f"30D average available: "
        f"{candles['average_30d'].notna().sum():,}"
    )


def main():

    for symbol in SYMBOLS:

        print("\n" + "=" * 50)
        print(f"Processing {symbol}")
        print("=" * 50)

        # -----------------------------------------------------
        # Calculate daily averages first
        # -----------------------------------------------------

        daily_averages = calculate_daily_averages(
            symbol
        )

        # -----------------------------------------------------
        # Attach averages to 1m, 3m and 5m candles
        # -----------------------------------------------------

        for timeframe in TIMEFRAMES:

            print(
                f"\nAttaching averages to {timeframe}..."
            )

            attach_to_timeframe(
                symbol,
                timeframe,
                daily_averages
            )

    print(
        "\nPart 8 average attachment complete."
    )


if __name__ == "__main__":
    main()