from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = ROOT / "data" / "processed"


ZONES = {
    "0_5": 0.005,
    "1_0": 0.010,
    "1_5": 0.015,
}

AVERAGES = {
    "7d": "average_7d",
    "15d": "average_15d",
    "30d": "average_30d",
}


def detect_touches(df):
    """
    Detect candle-level touches of long-term average zones.

    A candle touches a zone when its High-Low range
    overlaps the zone around the average.

    Rule:

        touch = high >= zone_low AND low <= zone_high

    This creates research touch flags only.
    It does NOT create trading signals.
    """

    for average_name, average_column in AVERAGES.items():

        for zone_name, zone_percentage in ZONES.items():

            zone_low = (
                df[average_column]
                * (1 - zone_percentage)
            )

            zone_high = (
                df[average_column]
                * (1 + zone_percentage)
            )

            touch_column = (
                f"touch_{average_name}_{zone_name}"
            )

            # Only allow a touch when the average exists.
            valid_average = df[average_column].notna()

            df[touch_column] = (
                valid_average
                & (df["high"] >= zone_low)
                & (df["low"] <= zone_high)
            )

    return df


def process(symbol, timeframe):
    input_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_distances.parquet"
    )

    output_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_touches.parquet"
    )

    print(f"\nProcessing {symbol} {timeframe}...")

    df = pd.read_parquet(input_path)

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    df = (
        df.sort_values("open_time")
        .reset_index(drop=True)
    )

    required_columns = [
        "open_time",
        "high",
        "low",
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

    df = detect_touches(df)

    df.to_parquet(
        output_path,
        index=False
    )

    touch_columns = [
        f"touch_{average}_{zone}"
        for average in AVERAGES
        for zone in ZONES
    ]

    print(f"Rows: {len(df):,}")
    print(f"Saved: {output_path}")

    print("\nTouch counts:")

    for column in touch_columns:
        count = int(df[column].sum())

        print(
            f"{column}: {count:,}"
        )


def main():
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            process(symbol, timeframe)

    print("\nPart 10 touch detection complete.")


if __name__ == "__main__":
    main()
