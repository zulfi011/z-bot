from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = ROOT / "data" / "processed"


def calculate_distances(df):
    """
    Calculate percentage distance between candle close
    and each long-term average.

    Formula:
        distance % = (close - average) / average * 100
    """

    averages = {
        "7d": "average_7d",
        "15d": "average_15d",
        "30d": "average_30d",
    }

    for period, average_column in averages.items():
        distance_column = f"distance_{period}_pct"

        df[distance_column] = (
            (df["close"] - df[average_column])
            / df[average_column]
            * 100
        )

    return df


def process(symbol, timeframe):
    input_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_averages.parquet"
    )

    output_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_distances.parquet"
    )

    print(f"\nProcessing {symbol} {timeframe}...")

    df = pd.read_parquet(input_path)

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    df = df.sort_values("open_time").reset_index(drop=True)

    required_columns = [
        "close",
        "average_7d",
        "average_15d",
        "average_30d",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    df = calculate_distances(df)

    df.to_parquet(
        output_path,
        index=False
    )

    print(f"Rows: {len(df):,}")
    print(f"Saved: {output_path}")

    for period in ["7d", "15d", "30d"]:
        column = f"distance_{period}_pct"

        valid_count = df[column].notna().sum()

        print(
            f"{column}: "
            f"{valid_count:,} valid values"
        )


def main():
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            process(symbol, timeframe)

    print("\nPart 9 distance calculation complete.")


if __name__ == "__main__":
    main()
