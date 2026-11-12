from pathlib import Path
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

PROCESSED_DIR = Path("data/processed")

TIMEFRAMES = {
    "3m": pd.Timedelta(minutes=3),
    "5m": pd.Timedelta(minutes=5),
}


def validate_dataset(symbol, timeframe, expected_interval):
    print()
    print("=" * 60)
    print(f"VALIDATING {symbol} {timeframe}")
    print("=" * 60)

    file_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}.parquet"
    )

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
        "quote_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if not missing_columns:
        print("✅ Required columns present")
        columns_ok = True
    else:
        print(f"❌ Missing columns: {missing_columns}")
        columns_ok = False

    # ---------------------------------------------------------
    # 2. Timestamp checks
    # ---------------------------------------------------------

    print("\n--- Timestamp Checks ---")

    timezone = getattr(df["open_time"].dt, "tz", None)

    if timezone is not None:
        print(f"Timezone: {timezone}")
        print("✅ Timestamps contain timezone information")
        timezone_ok = True
    else:
        print("❌ Timestamps have no timezone information")
        timezone_ok = False

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
    duplicate_timestamps = int(
        df["open_time"].duplicated().sum()
    )

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
    # 4. Interval / gap checks
    # ---------------------------------------------------------

    print("\n--- Interval Checks ---")

    time_diff = df["open_time"].diff()

    incorrect_intervals = time_diff[
        time_diff != expected_interval
    ].dropna()

    incorrect_interval_count = len(incorrect_intervals)

    print(
        f"Expected interval: "
        f"{expected_interval}"
    )

    print(
        f"Incorrect intervals: "
        f"{incorrect_interval_count:,}"
    )

    if incorrect_interval_count == 0:
        print(
            f"✅ All candles are exactly "
            f"{expected_interval} apart"
        )
        intervals_ok = True
    else:
        print("❌ Incorrect candle intervals found")

        print("\nExamples:")

        for timestamp, interval in (
            incorrect_intervals.head(10).items()
        ):
            print(f"  {timestamp}: {interval}")

        intervals_ok = False

    # ---------------------------------------------------------
    # 5. OHLC sanity checks
    # ---------------------------------------------------------

    print("\n--- OHLC Checks ---")

    invalid_high_low = int(
        (df["high"] < df["low"]).sum()
    )

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
    print(
        f"Open outside High/Low: "
        f"{invalid_open:,}"
    )
    print(
        f"Close outside High/Low: "
        f"{invalid_close:,}"
    )
    print(
        f"Non-positive prices: "
        f"{invalid_prices:,}"
    )

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

    negative_volume = int(
        (df["volume"] < 0).sum()
    )

    print(
        f"Negative volume values: "
        f"{negative_volume:,}"
    )

    if negative_volume == 0:
        print("✅ Volume looks sane")
        volume_ok = True
    else:
        print("❌ Negative volume values found")
        volume_ok = False

    # ---------------------------------------------------------
    # 7. Null / missing value checks
    # ---------------------------------------------------------

    print("\n--- Missing Value Checks ---")

    null_counts = df[required_columns].isna().sum()

    total_nulls = int(null_counts.sum())

    print(f"Total missing values: {total_nulls:,}")

    if total_nulls == 0:
        print("✅ No missing values")
        nulls_ok = True
    else:
        print("❌ Missing values found")

        for column, count in null_counts.items():
            if count > 0:
                print(f"  {column}: {count:,}")

        nulls_ok = False

    # ---------------------------------------------------------
    # 8. Dataset range
    # ---------------------------------------------------------

    print("\n--- Dataset Range ---")

    first_candle = df["open_time"].min()
    last_candle = df["open_time"].max()

    print(f"First candle: {first_candle}")
    print(f"Last candle:  {last_candle}")

    # ---------------------------------------------------------
    # 9. Overall status
    # ---------------------------------------------------------

    overall_status = (
        columns_ok
        and timezone_ok
        and sorted_ok
        and duplicate_rows == 0
        and duplicate_timestamps == 0
        and intervals_ok
        and ohlc_ok
        and volume_ok
        and nulls_ok
    )

    if overall_status:
        print("\n✅ OVERALL STATUS: PASS")
    else:
        print("\n❌ OVERALL STATUS: FAIL")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": len(df),
        "first_candle": first_candle,
        "last_candle": last_candle,
        "timezone": str(timezone),
        "timestamps_sorted": sorted_ok,
        "duplicate_rows": duplicate_rows,
        "duplicate_timestamps": duplicate_timestamps,
        "expected_interval": str(expected_interval),
        "incorrect_intervals": incorrect_interval_count,
        "invalid_high_low": invalid_high_low,
        "invalid_open": invalid_open,
        "invalid_close": invalid_close,
        "invalid_prices": invalid_prices,
        "negative_volume": negative_volume,
        "total_nulls": total_nulls,
        "overall_status": (
            "PASS" if overall_status else "FAIL"
        ),
    }


def main():

    print("V1 Stage 1 - Validate Resampled Data")

    results = []

    for symbol in SYMBOLS:

        for timeframe, expected_interval in TIMEFRAMES.items():

            result = validate_dataset(
                symbol,
                timeframe,
                expected_interval
            )

            results.append(result)

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    report_df = pd.DataFrame(results)

    print()
    print("=" * 60)
    print("RESAMPLED DATA VALIDATION COMPLETE")
    print("=" * 60)

    print()

    print(
        report_df[
            [
                "symbol",
                "timeframe",
                "rows",
                "incorrect_intervals",
                "duplicate_rows",
                "total_nulls",
                "overall_status",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()