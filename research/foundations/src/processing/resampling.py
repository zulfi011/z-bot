from pathlib import Path
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

TIMEFRAMES = {
    "3m": "3min",
    "5m": "5min",
}


def resample_symbol(symbol):
    print()
    print("=" * 60)
    print(f"PROCESSING {symbol}")
    print("=" * 60)

    # ---------------------------------------------------------
    # Load 1-minute data
    # ---------------------------------------------------------

    input_file = RAW_DIR / symbol / f"{symbol}_1m.parquet"

    print(f"Loading: {input_file}")

    df = pd.read_parquet(input_file)

    print(f"1-minute candles: {len(df):,}")

    # Make sure data is sorted
    df = df.sort_values("open_time").reset_index(drop=True)

    # Use open_time as the DataFrame index
    df = df.set_index("open_time")

    # ---------------------------------------------------------
    # Resampling rules
    # ---------------------------------------------------------

    aggregation = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "number_of_trades": "sum",
        "taker_buy_base_volume": "sum",
        "taker_buy_quote_volume": "sum",
    }

    # ---------------------------------------------------------
    # Create 3m and 5m datasets
    # ---------------------------------------------------------

    for timeframe, rule in TIMEFRAMES.items():

        print()
        print(f"Creating {timeframe} candles...")

        resampled = df.resample(
            rule,
            label="left",
            closed="left"
        ).agg(aggregation)

        # Remove periods where no 1-minute candles existed
        resampled = resampled.dropna(subset=["open"])

        # Recreate close_time
        duration = pd.Timedelta(rule)

        resampled["close_time"] = (
            resampled.index + duration - pd.Timedelta(microseconds=1)
        )

        # Move open_time back from index to column
        resampled = resampled.reset_index()

        # Keep columns in a consistent order
        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]

        resampled = resampled[columns]

        # -----------------------------------------------------
        # Save
        # -----------------------------------------------------

        output_dir = PROCESSED_DIR / symbol
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{symbol}_{timeframe}.parquet"

        resampled.to_parquet(output_file, index=False)

        print(f"Saved: {output_file}")
        print(f"Candles: {len(resampled):,}")
        print(f"First candle: {resampled['open_time'].min()}")
        print(f"Last candle:  {resampled['open_time'].max()}")

    print()
    print(f"✅ {symbol} processing complete")


def main():

    print("V1 Stage 1 - Create 3m & 5m Candles")
    print()

    for symbol in SYMBOLS:
        resample_symbol(symbol)

    print()
    print("=" * 60)
    print("RESAMPLING COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
