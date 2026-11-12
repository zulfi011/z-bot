
from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "results" / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_available_closes(symbol):
    path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_available_closes.parquet"
    )

    df = pd.read_parquet(path)

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True
    )

    df = df.sort_values("open_time").reset_index(drop=True)

    return df


def create_expected_averages(daily):
    result = daily[
        [
            "open_time",
            "available_daily_close",
        ]
    ].copy()

    result["average_7d"] = (
        result["available_daily_close"]
        .rolling(window=7, min_periods=7)
        .mean()
    )

    result["average_15d"] = (
        result["available_daily_close"]
        .rolling(window=15, min_periods=15)
        .mean()
    )

    result["average_30d"] = (
        result["available_daily_close"]
        .rolling(window=30, min_periods=30)
        .mean()
    )

    return result


def validate_timeframe(symbol, timeframe, expected_daily):
    source_path = (
        RAW_DIR / symbol / f"{symbol}_1m.parquet"
        if timeframe == "1m"
        else PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}.parquet"
    )

    attached_path = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_averages.parquet"
    )

    source = pd.read_parquet(source_path)
    attached = pd.read_parquet(attached_path)

    source["open_time"] = pd.to_datetime(
        source["open_time"],
        utc=True
    )

    attached["open_time"] = pd.to_datetime(
        attached["open_time"],
        utc=True
    )

    checks = {
        "symbol": symbol,
        "timeframe": timeframe,
        "source_rows": len(source),
        "attached_rows": len(attached),
        "row_count_match": len(source) == len(attached),
        "required_average_columns": all(
            column in attached.columns
            for column in [
                "average_7d",
                "average_15d",
                "average_30d",
            ]
        ),
        "utc": str(attached["open_time"].dt.tz) == "UTC",
        "sorted": attached["open_time"].is_monotonic_increasing,
        "duplicate_timestamps": int(
            attached["open_time"].duplicated().sum()
        ),
    }

    # Recreate exactly what the attachment process should have produced.
    expected = pd.merge_asof(
        attached[["open_time"]],
        expected_daily,
        on="open_time",
        direction="backward",
    )

    average_columns = [
        "average_7d",
        "average_15d",
        "average_30d",
    ]

    comparison_results = {}

    for column in average_columns:
        actual = attached[column].to_numpy()
        expected_values = expected[column].to_numpy()

        actual_nan = pd.isna(actual)
        expected_nan = pd.isna(expected_values)

        nan_match = np.array_equal(
            actual_nan,
            expected_nan
        )

        value_match = True

        valid_mask = ~actual_nan & ~expected_nan

        if valid_mask.any():
            value_match = np.allclose(
                actual[valid_mask],
                expected_values[valid_mask],
                rtol=1e-10,
                atol=1e-8,
            )

        comparison_results[column] = (
            nan_match and value_match
        )

    checks["average_7d_matches_expected"] = (
        comparison_results["average_7d"]
    )

    checks["average_15d_matches_expected"] = (
        comparison_results["average_15d"]
    )

    checks["average_30d_matches_expected"] = (
        comparison_results["average_30d"]
    )

    # Verify that an attached average never comes from a future daily date.
    expected_with_source = pd.merge_asof(
        attached[["open_time"]],
        expected_daily[
            [
                "open_time",
                "average_7d",
                "average_15d",
                "average_30d",
            ]
        ],
        on="open_time",
        direction="backward",
    )

    source_date_valid = (
        expected_with_source["open_time"]
        <= attached["open_time"]
    )

    checks["no_future_average_source"] = (
        source_date_valid.all()
    )

    checks["overall_pass"] = all(
        [
            checks["row_count_match"],
            checks["required_average_columns"],
            checks["utc"],
            checks["sorted"],
            checks["duplicate_timestamps"] == 0,
            checks["average_7d_matches_expected"],
            checks["average_15d_matches_expected"],
            checks["average_30d_matches_expected"],
            checks["no_future_average_source"],
        ]
    )

    return checks


def main():
    results = []

    for symbol in SYMBOLS:
        print(f"\nValidating {symbol}...")

        daily = load_available_closes(symbol)
        expected_daily = create_expected_averages(daily)

        for timeframe in TIMEFRAMES:
            result = validate_timeframe(
                symbol,
                timeframe,
                expected_daily,
            )

            results.append(result)

            status = "PASS" if result["overall_pass"] else "FAIL"

            print(
                f"{symbol} {timeframe}: {status}"
            )

    report = pd.DataFrame(results)

    report_path = (
        REPORT_DIR
        / "attached_averages_validation.csv"
    )

    report.to_csv(report_path, index=False)

    print("\n" + "=" * 60)
    print("PART 8 VALIDATION")
    print("=" * 60)

    print(
        report[
            [
                "symbol",
                "timeframe",
                "source_rows",
                "attached_rows",
                "average_7d_matches_expected",
                "average_15d_matches_expected",
                "average_30d_matches_expected",
                "no_future_average_source",
                "overall_pass",
            ]
        ].to_string(index=False)
    )

    if report["overall_pass"].all():
        print("\nPart 8 validation PASSED.")
        print(
            f"Report saved to: {report_path}"
        )
    else:
        print("\nPart 8 validation FAILED.")
        print(
            "Check the validation report for details."
        )


if __name__ == "__main__":
    main()