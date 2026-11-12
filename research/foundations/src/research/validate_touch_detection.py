from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

AVERAGES = {
    "7d": "average_7d",
    "15d": "average_15d",
    "30d": "average_30d",
}

ZONES = {
    "0_5": 0.005,
    "1_0": 0.010,
    "1_5": 0.015,
}


def get_input_path(symbol, timeframe):
    return Path(
        f"data/processed/{symbol}/{symbol}_{timeframe}_with_distances.parquet"
    )


def get_touch_path(symbol, timeframe):
    return Path(
        f"data/processed/{symbol}/{symbol}_{timeframe}_with_touches.parquet"
    )


def validate_dataset(symbol, timeframe):
    input_path = get_input_path(symbol, timeframe)
    touch_path = get_touch_path(symbol, timeframe)

    source = pd.read_parquet(input_path)
    df = pd.read_parquet(touch_path)

    checks = {}

    # ---------------------------------------------------------
    # 1. Row count
    # ---------------------------------------------------------
    checks["row_count_match"] = len(source) == len(df)

    # ---------------------------------------------------------
    # 2. Required touch columns
    # ---------------------------------------------------------
    touch_columns = []

    for average_name in AVERAGES:
        for zone_name in ZONES:
            column = f"touch_{average_name}_{zone_name}"
            touch_columns.append(column)

    checks["all_touch_columns_present"] = all(
        column in df.columns for column in touch_columns
    )

    # ---------------------------------------------------------
    # 3. Touch columns are boolean
    # ---------------------------------------------------------
    checks["touch_columns_boolean"] = all(
        pd.api.types.is_bool_dtype(df[column])
        for column in touch_columns
    )

    # ---------------------------------------------------------
    # 4. UTC timestamps
    # ---------------------------------------------------------
    checks["timestamps_utc"] = (
        pd.api.types.is_datetime64tz_dtype(df["open_time"])
        and str(df["open_time"].dt.tz) == "UTC"
    )

    # ---------------------------------------------------------
    # 5. Sorted timestamps
    # ---------------------------------------------------------
    checks["timestamps_sorted"] = df["open_time"].is_monotonic_increasing

    # ---------------------------------------------------------
    # 6. No duplicate timestamps
    # ---------------------------------------------------------
    checks["duplicate_timestamps"] = (
        df["open_time"].duplicated().sum() == 0
    )

    # ---------------------------------------------------------
    # 7. No missing touch values
    # ---------------------------------------------------------
    checks["no_missing_touch_values"] = not df[touch_columns].isna().any().any()

    # ---------------------------------------------------------
    # 8. Exact touch-rule validation
    # ---------------------------------------------------------
    exact_rule_pass = True

    for average_name, average_column in AVERAGES.items():

        average = df[average_column]

        for zone_name, zone_percentage in ZONES.items():

            touch_column = f"touch_{average_name}_{zone_name}"

            zone_low = average * (1 - zone_percentage)
            zone_high = average * (1 + zone_percentage)

            valid_average = average.notna()

            expected_touch = (
                valid_average
                & (df["high"] >= zone_low)
                & (df["low"] <= zone_high)
            )

            actual_touch = df[touch_column]

            if not (actual_touch == expected_touch).all():
                exact_rule_pass = False

    checks["exact_touch_rule"] = exact_rule_pass

    # ---------------------------------------------------------
    # 9. No touch when average is unavailable
    # ---------------------------------------------------------
    unavailable_average_pass = True

    for average_name, average_column in AVERAGES.items():

        average_missing = df[average_column].isna()

        for zone_name in ZONES:

            touch_column = f"touch_{average_name}_{zone_name}"

            if df.loc[average_missing, touch_column].any():
                unavailable_average_pass = False

    checks["no_touch_without_average"] = unavailable_average_pass

    # ---------------------------------------------------------
    # 10. Zone nesting
    # ---------------------------------------------------------
    nesting_pass = True

    for average_name in AVERAGES:

        narrow = df[f"touch_{average_name}_0_5"]
        medium = df[f"touch_{average_name}_1_0"]
        wide = df[f"touch_{average_name}_1_5"]

        if not (narrow <= medium).all():
            nesting_pass = False

        if not (medium <= wide).all():
            nesting_pass = False

    checks["zone_nesting"] = nesting_pass

    # ---------------------------------------------------------
    # Overall result
    # ---------------------------------------------------------
    checks["overall_pass"] = all(checks.values())

    return checks


def main():
    results = []

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:

            print(f"Validating {symbol} {timeframe}...")

            checks = validate_dataset(symbol, timeframe)

            row = {
                "symbol": symbol,
                "timeframe": timeframe,
                **checks,
            }

            results.append(row)

            status = "PASS" if checks["overall_pass"] else "FAIL"
            print(f"  {status}")

    results_df = pd.DataFrame(results)

    output_path = Path("results/reports/touch_detection_validation.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results_df.to_csv(output_path, index=False)

    print()
    print("=" * 60)
    print("TOUCH DETECTION VALIDATION")
    print("=" * 60)

    print(results_df.to_string(index=False))

    print()
    print(f"Report saved to: {output_path}")

    if results_df["overall_pass"].all():
        print("OVERALL RESULT: PASS")
    else:
        print("OVERALL RESULT: FAIL")


if __name__ == "__main__":
    main()
