from pathlib import Path
from datetime import date
import io
import zipfile

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

START_DATE = date(2024, 9, 1)
END_DATE = date(2026, 8, 31)

INTERVAL = "1m"

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

RAW_DIR = Path("data/raw")


# ============================================================
# BINANCE COLUMNS
# ============================================================

COLUMNS = [
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
    "ignore",
]


# ============================================================
# DOWNLOAD ONE MONTH
# ============================================================

def download_month(symbol, year, month):
    month_str = f"{year}-{month:02d}"
    filename = f"{symbol}-{INTERVAL}-{month_str}.zip"

    url = f"{BASE_URL}/{symbol}/{INTERVAL}/{filename}"

    print(f"Downloading {filename} ...")

    response = requests.get(url, timeout=60)

    if response.status_code == 404:
        print(f"  Not found: {filename}")
        return None

    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:

        csv_files = [
            name
            for name in archive.namelist()
            if name.endswith(".csv")
        ]

        if not csv_files:
            raise ValueError(
                f"No CSV found inside {filename}"
            )

        with archive.open(csv_files[0]) as file:
            df = pd.read_csv(
                file,
                header=None,
                names=COLUMNS
            )

        # Binance historical files use different timestamp units
        # depending on the data period.
        timestamp = df["open_time"].iloc[0]

        if timestamp > 10**14:
            timestamp_unit = "us"
        else:
            timestamp_unit = "ms"

        df["open_time"] = pd.to_datetime(
            df["open_time"],
            unit=timestamp_unit,
            utc=True
        )

        df["close_time"] = pd.to_datetime(
            df["close_time"],
            unit=timestamp_unit,
            utc=True
        )

    print(f"  Loaded {len(df):,} candles")

    return df


# ============================================================
# DOWNLOAD ONE SYMBOL
# ============================================================

def download_symbol(symbol):

    print()
    print("=" * 60)
    print(f"Downloading {symbol}")
    print("=" * 60)

    monthly_data = []

    current_year = START_DATE.year
    current_month = START_DATE.month

    while (
        current_year < END_DATE.year
        or (
            current_year == END_DATE.year
            and current_month <= END_DATE.month
        )
    ):

        df = download_month(
            symbol,
            current_year,
            current_month
        )

        if df is not None:
            monthly_data.append(df)

        # Move to next month
        if current_month == 12:
            current_year += 1
            current_month = 1
        else:
            current_month += 1

    if not monthly_data:
        raise RuntimeError(
            f"No data downloaded for {symbol}"
        )

    print()
    print(f"Combining {len(monthly_data)} monthly files...")

    df = pd.concat(
        monthly_data,
        ignore_index=True
    )


    # ========================================================
    # CONVERT NUMERIC COLUMNS
    # ========================================================

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    before = len(df)

    df = df.drop_duplicates(
        subset=["open_time"]
    )

    duplicates_removed = before - len(df)

    # ========================================================
    # SORT
    # ========================================================

    df = df.sort_values(
        "open_time"
    ).reset_index(drop=True)

    # ========================================================
    # FILTER EXACT DATE RANGE
    # ========================================================

    start_timestamp = pd.Timestamp(
        START_DATE,
        tz="UTC"
    )

    # END_DATE is inclusive, so use the next day
    end_timestamp = (
        pd.Timestamp(
            END_DATE,
            tz="UTC"
        )
        + pd.Timedelta(days=1)
    )

    df = df[
        (df["open_time"] >= start_timestamp)
        & (df["open_time"] < end_timestamp)
    ].reset_index(drop=True)

    # ========================================================
    # SAVE PARQUET
    # ========================================================

    output_dir = RAW_DIR / symbol
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        output_dir /
        f"{symbol}_1m.parquet"
    )

    df.to_parquet(
        output_file,
        index=False
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print(f"Saved: {output_file}")
    print(f"Rows: {len(df):,}")
    print(f"Duplicates removed: {duplicates_removed:,}")
    print(f"First candle: {df['open_time'].min()}")
    print(f"Last candle:  {df['open_time'].max()}")
    print(f"File size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")

    return df


# ============================================================
# MAIN
# ============================================================

def main():

    print("V1 Stage 1 - Historical Data Downloader")
    print()
    print(f"Period: {START_DATE} → {END_DATE}")
    print(f"Interval: {INTERVAL}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print()

    for symbol in SYMBOLS:
        download_symbol(symbol)

    print()
    print("=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()