from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "results" / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)


def validate_dataset(symbol, timeframe):
    input_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_averages.parquet"
    )

    distance_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_distances.parquet"
    )

    print(f"\nValidating {symbol} {timeframe}...")

    original = pd.read_parquet(input_path)
    df = pd.read_parquet(distance_path)

    # Make sure timestamps are UTC
    original["open_time"] = pd.to_datetime(
        original["open_time"],
        utc=True
    )

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    # Required columns
    required_columns = [
        "open_time",
        "close",
        "average_7d",
        "average_15d",
        "average_30d",
        "distance_7d_pct",
        "distance_15d_pct",
        "distance_30d_pct",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    row_count_match = len(original) == len(df)

    utc_valid = str(df["open_time"].dt.tz) == "UTC"

    sorted_valid = df["open_time"].is_monotonic_increasing

    duplicate_timestamps = int(
        df["open_time"].duplicated().sum()
    )

    # ---------------------------------------------------------
    # Validate distance calculations
    # ---------------------------------------------------------

    distance_checks = {}

    periods = ["7d", "15d", "30d"]

    for period in periods:
        average_column = f"average_{period}"
        distance_column = f"distance_{period}_pct"

        expected = (
            (df["close"] - df[average_column])
            / df[average_column]
            * 100
        )

        actual = df[distance_column]

        # Only compare rows where an average exists.
        valid_mask = (
            df[average_column].notna()
            & actual.notna()
        )

        values_match = np.allclose(
            actual[valid_mask].to_numpy(),
            expected[valid_mask].to_numpy(),
            rtol=1e-10,
            atol=1e-8,
        )

        distance_checks[period] = values_match

    # ---------------------------------------------------------
    # Validate NaN pattern
    # ---------------------------------------------------------

    nan_pattern_checks = {}

    for period in periods:
        average_column = f"average_{period}"
        distance_column = f"distance_{period}_pct"

        average_nan = df[average_column].isna()
        distance_nan = df[distance_column].isna()

        nan_pattern_checks[period] = (
            average_nan.equals(distance_nan)
        )

    # ---------------------------------------------------------
    # Validate infinite values
    # ---------------------------------------------------------

    infinite_checks = {}

    for period in periods:
        distance_column = f"distance_{period}_pct"

        infinite_count = np.isinf(
            df[distance_column].dropna().to_numpy()
        ).sum()

        infinite_checks[period] = infinite_count == 0

    # ---------------------------------------------------------
    # Build result
    # ---------------------------------------------------------

    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "source_rows": len(original),
        "distance_rows": len(df),
        "row_count_match": row_count_match,
        "required_columns_present": len(missing_columns) == 0,
        "missing_columns": ", ".join(missing_columns),
        "utc": utc_valid,
        "sorted": sorted_valid,
        "duplicate_timestamps": duplicate_timestamps,

        "distance_7d_matches_formula":
            distance_checks["7d"],

        "distance_15d_matches_formula":
            distance_checks["15d"],

        "distance_30d_matches_formula":
            distance_checks["30d"],

        "distance_7d_nan_pattern_correct":
            nan_pattern_checks["7d"],

        "distance_15d_nan_pattern_correct":
            nan_pattern_checks["15d"],

        "distance_30d_nan_pattern_correct":
            nan_pattern_checks["30d"],

        "distance_7d_no_infinite_values":
            infinite_checks["7d"],

        "distance_15d_no_infinite_values":
            infinite_checks["15d"],

        "distance_30d_no_infinite_values":
            infinite_checks["30d"],
    }

    result["overall_pass"] = all([
        result["row_count_match"],
        result["required_columns_present"],
        result["utc"],
        result["sorted"],
        result["duplicate_timestamps"] == 0,

        result["distance_7d_matches_formula"],
        result["distance_15d_matches_formula"],
        result["distance_30d_matches_formula"],

        result["distance_7d_nan_pattern_correct"],
        result["distance_15d_nan_pattern_correct"],
        result["distance_30d_nan_pattern_correct"],

        result["distance_7d_no_infinite_values"],
        result["distance_15d_no_infinite_values"],
        result["distance_30d_no_infinite_values"],
    ])

    status = "PASS" if result["overall_pass"] else "FAIL"

    print(f"{symbol} {timeframe}: {status}")

    return result


def main():
    results = []

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            result = validate_dataset(
                symbol,
                timeframe
            )

            results.append(result)

    report = pd.DataFrame(results)

    report_path = (
        REPORT_DIR
        / "distance_validation.csv"
    )

    report.to_csv(
        report_path,
        index=False
    )

    print("\n" + "=" * 60)
    print("PART 9 VALIDATION")
    print("=" * 60)

    print(
        report[
            [
                "symbol",
                "timeframe",
                "source_rows",
                "distance_rows",
                "row_count_match",
                "distance_7d_matches_formula",
                "distance_15d_matches_formula",
                "distance_30d_matches_formula",
                "distance_7d_no_infinite_values",
                "distance_15d_no_infinite_values",
                "distance_30d_no_infinite_values",
                "overall_pass",
            ]
        ].to_string(index=False)
    )

    print("\n" + "=" * 60)

    if report["overall_pass"].all():
        print("Part 9 validation PASSED.")
        print(f"Report saved to: {report_path}")
    else:
        print("Part 9 validation FAILED.")
        print(f"Check the report: {report_path}")


if __name__ == "__main__":
    main()