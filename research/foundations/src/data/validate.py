from pathlib import Path
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

RAW_DIR = Path("data/raw")
REPORT_DIR = Path("results/reports")

EXPECTED_INTERVAL = pd.Timedelta(minutes=1)


def validate_symbol(symbol):
    print()
    print("=" * 60)
    print(f"VALIDATING {symbol}")
    print("=" * 60)

    file_path = RAW_DIR / symbol / f"{symbol}_1m.parquet"

    df = pd.read_parquet(file_path)

    print(f"Rows: {len(df):,}")

    # ---------------------------------------------------------
    # 1. Required columns
    # ---------------------------------------------------------

    required_columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    required_columns_ok = len(missing_columns) == 0

    if required_columns_ok:
        print("✅ Required columns present")
    else:
        print(f"❌ Missing columns: {missing_columns}")

    # ---------------------------------------------------------
    # 2. Timestamp checks
    # ---------------------------------------------------------

    print("\n--- Timestamp Checks ---")

    timestamp_dtype = str(df["open_time"].dtype)

    print(f"Timestamp dtype: {timestamp_dtype}")

    timezone = getattr(df["open_time"].dt, "tz", None)

    utc_ok = timezone is not None

    if utc_ok:
        print(f"Timezone: {timezone}")
        print("✅ Timestamps contain timezone information")
    else:
        print("❌ Timestamps have no timezone information")

    sorted_ok = df["open_time"].is_monotonic_increasing

    if sorted_ok:
        print("✅ Timestamps are sorted")
    else:
        print("❌ Timestamps are NOT sorted")

    # ---------------------------------------------------------
    # 3. Duplicate checks
    # ---------------------------------------------------------

    print("\n--- Duplicate Checks ---")

    duplicate_rows = int(df.duplicated().sum())
    duplicate_timestamps = int(df["open_time"].duplicated().sum())

    print(f"Duplicate rows: {duplicate_rows:,}")
    print(f"Duplicate timestamps: {duplicate_timestamps:,}")

    if duplicate_rows == 0:
        print("✅ No duplicate rows")
    else:
        print("❌ Duplicate rows found")

    if duplicate_timestamps == 0:
        print("✅ No duplicate timestamps")
    else:
        print("❌ Duplicate timestamps found")

    # ---------------------------------------------------------
    # 4. Missing candle / gap checks
    # ---------------------------------------------------------

    print("\n--- Gap Checks ---")

    time_diff = df["open_time"].diff()

    gaps = time_diff[time_diff > EXPECTED_INTERVAL]

    gap_count = len(gaps)

    print(f"Number of gaps: {gap_count:,}")

    largest_gap = gaps.max() if gap_count > 0 else pd.Timedelta(0)

    if gap_count > 0:
        print("❌ Gaps found")

        print("\nLargest gaps:")

        largest_gaps = gaps.sort_values(ascending=False).head(10)

        for timestamp, gap in largest_gaps.items():
            print(f"  {timestamp}: {gap}")
    else:
        print("✅ No missing 1-minute candles")

    # ---------------------------------------------------------
    # 5. OHLC sanity checks
    # ---------------------------------------------------------

    print("\n--- OHLC Checks ---")

    invalid_high_low = int((df["high"] < df["low"]).sum())

    invalid_open = int(
        (
            (df["open"] > df["high"]) |
            (df["open"] < df["low"])
        ).sum()
    )

    invalid_close = int(
        (
            (df["close"] > df["high"]) |
            (df["close"] < df["low"])
        ).sum()
    )

    invalid_prices = int(
        (
            (df["open"] <= 0) |
            (df["high"] <= 0) |
            (df["low"] <= 0) |
            (df["close"] <= 0)
        ).sum()
    )

    print(f"High < Low: {invalid_high_low:,}")
    print(f"Open outside High/Low: {invalid_open:,}")
    print(f"Close outside High/Low: {invalid_close:,}")
    print(f"Non-positive prices: {invalid_prices:,}")

    ohlc_ok = (
        invalid_high_low == 0
        and invalid_open == 0
        and invalid_close == 0
        and invalid_prices == 0
    )

    if ohlc_ok:
        print("✅ OHLC data looks sane")
    else:
        print("❌ OHLC problems found")

    # ---------------------------------------------------------
    # 6. Volume checks
    # ---------------------------------------------------------

    print("\n--- Volume Checks ---")

    invalid_volume = int((df["volume"] < 0).sum())

    print(f"Negative volume values: {invalid_volume:,}")

    volume_ok = invalid_volume == 0

    if volume_ok:
        print("✅ Volume looks sane")
    else:
        print("❌ Negative volume values found")

    # ---------------------------------------------------------
    # 7. Dataset information
    # ---------------------------------------------------------

    first_candle = df["open_time"].min()
    last_candle = df["open_time"].max()

    print("\n--- Dataset Range ---")

    print(f"First candle: {first_candle}")
    print(f"Last candle:  {last_candle}")

    # ---------------------------------------------------------
    # 8. Overall status
    # ---------------------------------------------------------

    overall_status = (
        required_columns_ok
        and utc_ok
        and sorted_ok
        and duplicate_rows == 0
        and duplicate_timestamps == 0
        and gap_count == 0
        and ohlc_ok
        and volume_ok
    )

    if overall_status:
        print("\n✅ OVERALL STATUS: PASS")
    else:
        print("\n❌ OVERALL STATUS: FAIL")

    # ---------------------------------------------------------
    # 9. Return report data
    # ---------------------------------------------------------

    return {
        "symbol": symbol,
        "rows": len(df),
        "first_candle": first_candle,
        "last_candle": last_candle,
        "timestamp_dtype": timestamp_dtype,
        "timezone": str(timezone),
        "timestamps_sorted": sorted_ok,
        "duplicate_rows": duplicate_rows,
        "duplicate_timestamps": duplicate_timestamps,
        "gap_count": gap_count,
        "largest_gap": str(largest_gap),
        "invalid_high_low": invalid_high_low,
        "invalid_open": invalid_open,
        "invalid_close": invalid_close,
        "invalid_prices": invalid_prices,
        "negative_volume": invalid_volume,
        "overall_status": "PASS" if overall_status else "FAIL",
    }


def main():

    print("V1 Stage 1 - Raw Data Validation")

    results = []

    for symbol in SYMBOLS:
        result = validate_symbol(symbol)
        results.append(result)

    # ---------------------------------------------------------
    # Create report directory
    # ---------------------------------------------------------

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # Save validation report
    # ---------------------------------------------------------

    report_df = pd.DataFrame(results)

    report_file = REPORT_DIR / "raw_data_validation.csv"

    report_df.to_csv(report_file, index=False)

    print()
    print("=" * 60)
    print("VALIDATION COMPLETE")
    print("=" * 60)

    print(f"\nReport saved to:")
    print(report_file)

    print("\nSummary:")
    print(report_df[["symbol", "rows", "gap_count", "duplicate_rows", "overall_status"]])


if __name__ == "__main__":
    main()
