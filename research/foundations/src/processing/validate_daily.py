from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

PROCESSED_DIR = Path("data/processed")
REPORT_DIR = Path("results/reports")


REQUIRED_COLUMNS = [
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


def validate_daily_data(symbol: str):
    file_path = PROCESSED_DIR / symbol / f"{symbol}_1d.parquet"

    print(f"\nValidating {symbol}...")

    df = pd.read_parquet(file_path)

    results = {}

    # ---------------------------------------------------------
    # 1. Required columns
    # ---------------------------------------------------------
    results["required_columns"] = all(
        column in df.columns for column in REQUIRED_COLUMNS
    )

    # ---------------------------------------------------------
    # 2. Timestamp type and UTC
    # ---------------------------------------------------------
    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    df["close_time"] = pd.to_datetime(
        df["close_time"],
        utc=True
    )

    results["timestamps_utc"] = (
        df["open_time"].dt.tz is not None
        and df["close_time"].dt.tz is not None
    )

    # ---------------------------------------------------------
    # 3. Sorted timestamps
    # ---------------------------------------------------------
    results["sorted"] = df["open_time"].is_monotonic_increasing

    # ---------------------------------------------------------
    # 4. Duplicate rows
    # ---------------------------------------------------------
    results["duplicate_rows"] = int(df.duplicated().sum())

    # ---------------------------------------------------------
    # 5. Duplicate timestamps
    # ---------------------------------------------------------
    results["duplicate_timestamps"] = int(
        df["open_time"].duplicated().sum()
    )

    # ---------------------------------------------------------
    # 6. Daily interval
    # ---------------------------------------------------------
    intervals = df["open_time"].diff().dropna()

    results["incorrect_intervals"] = int(
        (intervals != pd.Timedelta(days=1)).sum()
    )

    # ---------------------------------------------------------
    # 7. OHLC validity
    # ---------------------------------------------------------
    results["high_less_than_low"] = int(
        (df["high"] < df["low"]).sum()
    )

    results["open_outside_range"] = int(
        ((df["open"] > df["high"]) |
         (df["open"] < df["low"])).sum()
    )

    results["close_outside_range"] = int(
        ((df["close"] > df["high"]) |
         (df["close"] < df["low"])).sum()
    )

    # ---------------------------------------------------------
    # 8. Positive prices
    # ---------------------------------------------------------
    results["non_positive_prices"] = int(
        (
            (df["open"] <= 0) |
            (df["high"] <= 0) |
            (df["low"] <= 0) |
            (df["close"] <= 0)
        ).sum()
    )

    # ---------------------------------------------------------
    # 9. Negative volume
    # ---------------------------------------------------------
    results["negative_volume"] = int(
        (
            (df["volume"] < 0) |
            (df["quote_volume"] < 0) |
            (df["number_of_trades"] < 0) |
            (df["taker_buy_base_volume"] < 0) |
            (df["taker_buy_quote_volume"] < 0)
        ).sum()
    )

    # ---------------------------------------------------------
    # 10. Missing values
    # ---------------------------------------------------------
    results["missing_values"] = int(df.isna().sum().sum())

    # ---------------------------------------------------------
    # 11. Row count
    # ---------------------------------------------------------
    results["rows"] = len(df)

    results["first_date"] = df["open_time"].min()
    results["last_date"] = df["open_time"].max()

    # ---------------------------------------------------------
    # Overall result
    # ---------------------------------------------------------
    results["overall"] = (
        results["required_columns"]
        and results["timestamps_utc"]
        and results["sorted"]
        and results["duplicate_rows"] == 0
        and results["duplicate_timestamps"] == 0
        and results["incorrect_intervals"] == 0
        and results["high_less_than_low"] == 0
        and results["open_outside_range"] == 0
        and results["close_outside_range"] == 0
        and results["non_positive_prices"] == 0
        and results["negative_volume"] == 0
        and results["missing_values"] == 0
    )

    print(f"Rows: {results['rows']:,}")
    print(f"First date: {results['first_date']}")
    print(f"Last date: {results['last_date']}")
    print(f"Duplicate timestamps: {results['duplicate_timestamps']}")
    print(f"Incorrect intervals: {results['incorrect_intervals']}")
    print(f"Missing values: {results['missing_values']}")
    print(f"Overall: {'PASS' if results['overall'] else 'FAIL'}")

    return results


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []

    for symbol in SYMBOLS:
        results = validate_daily_data(symbol)
        results["symbol"] = symbol
        all_results.append(results)

    report = pd.DataFrame(all_results)

    # Put symbol first
    columns = ["symbol"] + [
        column for column in report.columns
        if column != "symbol"
    ]

    report = report[columns]

    output_file = REPORT_DIR / "daily_data_validation.csv"

    report.to_csv(output_file, index=False)

    print(f"\nValidation report saved to: {output_file}")


if __name__ == "__main__":
    main()
