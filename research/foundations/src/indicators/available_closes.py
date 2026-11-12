from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

PROCESSED_DIR = Path("data/processed")


def create_available_closes(symbol: str):
    input_file = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_1d.parquet"
    )

    output_file = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_available_closes.parquet"
    )

    print(f"\nProcessing {symbol}...")

    # ---------------------------------------------------------
    # 1. Load validated daily data
    # ---------------------------------------------------------
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

    # Sort by date
    df = df.sort_values("open_time").reset_index(drop=True)

    # ---------------------------------------------------------
    # 2. Keep only the information needed for this stage
    # ---------------------------------------------------------
    available = df[
        [
            "open_time",
            "close_time",
            "close",
        ]
    ].copy()

    # ---------------------------------------------------------
    # 3. Shift the close by one day
    #
    # The close of a daily candle is only available AFTER
    # that candle has completed.
    #
    # Example:
    #
    # July 10 candle → July 10 close
    #
    # At the start of July 11:
    # available close = July 10 close
    #
    # Therefore we shift the close forward by one row.
    # ---------------------------------------------------------
    available["available_daily_close"] = (
        available["close"].shift(1)
    )

    available["available_close_date"] = (
        available["open_time"].shift(1)
    )

    # ---------------------------------------------------------
    # 4. Remove the first row
    #
    # There is no previous completed daily candle available
    # for the first day in our dataset.
    # ---------------------------------------------------------
    available = available.dropna(
        subset=["available_daily_close"]
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # 5. Keep only the columns needed
    # ---------------------------------------------------------
    available = available[
        [
            "open_time",
            "available_close_date",
            "available_daily_close",
        ]
    ]

    # ---------------------------------------------------------
    # 6. Save
    # ---------------------------------------------------------
    available.to_parquet(
        output_file,
        index=False
    )

    print(f"Saved: {output_file}")
    print(f"Rows: {len(available):,}")

    print(
        f"First research date: "
        f"{available['open_time'].min()}"
    )

    print(
        f"First available close date: "
        f"{available['available_close_date'].min()}"
    )

    print(
        f"Last research date: "
        f"{available['open_time'].max()}"
    )


def main():
    for symbol in SYMBOLS:
        create_available_closes(symbol)

    print("\nAvailable daily closes created successfully.")


if __name__ == "__main__":
    main()