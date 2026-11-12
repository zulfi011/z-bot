from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")


def create_daily_data(symbol: str):
    input_file = RAW_DIR / symbol / f"{symbol}_1m.parquet"
    output_dir = PROCESSED_DIR / symbol
    output_file = output_dir / f"{symbol}_1d.parquet"

    print(f"\nProcessing {symbol}...")

    # Load 1-minute data
    df = pd.read_parquet(input_file)

    # Make sure timestamps are UTC
    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    df["close_time"] = pd.to_datetime(
        df["close_time"],
        utc=True
    )

    # Sort by time
    df = df.sort_values("open_time").reset_index(drop=True)

    # Use open_time as index for resampling
    df = df.set_index("open_time")

    # Create daily candles
    daily = df.resample(
        "1D",
        label="left",
        closed="left"
    ).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "number_of_trades": "sum",
        "taker_buy_base_volume": "sum",
        "taker_buy_quote_volume": "sum",
    })

    # Remove empty days
    daily = daily.dropna(subset=["open", "high", "low", "close"])

    # Convert index back into open_time column
    daily = daily.reset_index()

    # Daily candle closes at the end of the UTC day.
    # Use 1 microsecond before the next day's midnight.
    daily["close_time"] = (
        daily["open_time"]
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    )

    # Make sure column order is consistent
    daily = daily[
        [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "close_time",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
    ]

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(output_file, index=False)

    print(f"Saved: {output_file}")
    print(f"Rows: {len(daily):,}")
    print(f"First day: {daily['open_time'].min()}")
    print(f"Last day:  {daily['open_time'].max()}")


def main():
    for symbol in SYMBOLS:
        create_daily_data(symbol)

    print("\nDaily data creation complete.")


if __name__ == "__main__":
    main()
