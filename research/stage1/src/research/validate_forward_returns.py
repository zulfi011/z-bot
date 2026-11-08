from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")
REPORT_DIR = Path("results/reports")


HORIZONS = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "24h": "24h",
}


def validate_dataset(
    symbol: str,
    timeframe: str,
) -> dict:

    print(f"\nValidating {symbol} {timeframe}")

    event_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events.parquet"
    )

    result_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_returns.parquet"
    )

    raw_file = (
        RAW_DIR
        / symbol
        / f"{symbol}_1m.parquet"
    )

    checks = {}

    # ---------------------------------------------------------
    # 1. Files exist
    # ---------------------------------------------------------

    checks["event_file_exists"] = event_file.exists()
    checks["result_file_exists"] = result_file.exists()
    checks["raw_file_exists"] = raw_file.exists()

    if not all(
        [
            checks["event_file_exists"],
            checks["result_file_exists"],
            checks["raw_file_exists"],
        ]
    ):
        checks["overall_pass"] = False
        return checks

    # ---------------------------------------------------------
    # Load data
    # ---------------------------------------------------------

    events = pd.read_parquet(event_file)

    results = pd.read_parquet(result_file)

    raw = pd.read_parquet(
        raw_file,
        columns=[
            "open_time",
            "close",
        ],
    )

    events["timestamp"] = pd.to_datetime(
        events["timestamp"],
        utc=True,
    )

    results["timestamp"] = pd.to_datetime(
        results["timestamp"],
        utc=True,
    )

    raw["open_time"] = pd.to_datetime(
        raw["open_time"],
        utc=True,
    )

    # ---------------------------------------------------------
    # 2. Row count preserved
    # ---------------------------------------------------------

    checks["row_count_match"] = (
        len(events) == len(results)
    )

    # ---------------------------------------------------------
    # 3. Required columns
    # ---------------------------------------------------------

    required_columns = list(events.columns)

    for horizon_name in HORIZONS:
        required_columns.extend(
            [
                f"future_price_{horizon_name}",
                f"return_{horizon_name}_pct",
            ]
        )

    checks["required_columns"] = all(
        column in results.columns
        for column in required_columns
    )

    # ---------------------------------------------------------
    # 4. Event IDs preserved
    # ---------------------------------------------------------

    checks["event_ids_unique"] = (
        results["event_id"].duplicated().sum() == 0
    )

    checks["event_ids_match"] = (
        set(events["event_id"])
        == set(results["event_id"])
    )

    # ---------------------------------------------------------
    # 5. Core Part 11 data unchanged
    # ---------------------------------------------------------

    original_columns = list(events.columns)

    left = events[
        original_columns
    ].sort_values(
        "event_id"
    ).reset_index(drop=True)

    right = results[
        original_columns
    ].sort_values(
        "event_id"
    ).reset_index(drop=True)

    checks["part11_data_preserved"] = left.equals(right)

    # ---------------------------------------------------------
    # 6. Timestamp checks
    # ---------------------------------------------------------

    checks["timestamp_utc"] = (
        str(results["timestamp"].dtype)
        == "datetime64[us, UTC]"
        or str(results["timestamp"].dtype)
        == "datetime64[ns, UTC]"
        or str(results["timestamp"].dtype).endswith(", UTC]")
    )

    checks["timestamps_sorted"] = (
        results["timestamp"].is_monotonic_increasing
    )

    # ---------------------------------------------------------
    # Prepare raw lookup
    # ---------------------------------------------------------

    raw_lookup = (
        raw
        .drop_duplicates(subset=["open_time"])
        .set_index("open_time")["close"]
    )

    raw_min_time = raw["open_time"].min()
    raw_max_time = raw["open_time"].max()

    # ---------------------------------------------------------
    # Validate each horizon
    # ---------------------------------------------------------

    for horizon_name, horizon_delta in HORIZONS.items():

        print(f"  Checking {horizon_name}")

        future_price_column = (
            f"future_price_{horizon_name}"
        )

        return_column = (
            f"return_{horizon_name}_pct"
        )

        target_timestamp = (
            results["timestamp"]
            + pd.Timedelta(horizon_delta)
        )

        # -----------------------------------------------------
        # Expected future prices
        # -----------------------------------------------------

        expected_future_price = (
            target_timestamp.map(raw_lookup)
        )

        actual_future_price = (
            results[future_price_column]
        )

        # -----------------------------------------------------
        # 7. Exact future price match
        # -----------------------------------------------------

        price_match = (
            (
                expected_future_price.isna()
                & actual_future_price.isna()
            )
            |
            np.isclose(
                expected_future_price.fillna(0),
                actual_future_price.fillna(0),
                rtol=1e-12,
                atol=1e-12,
            )
        )

        checks[
            f"{horizon_name}_future_price_match"
        ] = bool(price_match.all())

        # -----------------------------------------------------
        # 8. Return formula exact
        # -----------------------------------------------------

        expected_return = (
            (
                expected_future_price
                - results["price"]
            )
            / results["price"]
            * 100
        )

        actual_return = (
            results[return_column]
        )

        return_match = (
            (
                expected_return.isna()
                & actual_return.isna()
            )
            |
            np.isclose(
                expected_return.fillna(0),
                actual_return.fillna(0),
                rtol=1e-10,
                atol=1e-10,
            )
        )

        checks[
            f"{horizon_name}_return_formula"
        ] = bool(return_match.all())

        # -----------------------------------------------------
        # 9. NaN pattern must match exact target availability
        # -----------------------------------------------------

        checks[
            f"{horizon_name}_nan_pattern"
        ] = (
            expected_future_price.isna()
            .equals(
                actual_future_price.isna()
            )
        )

        # -----------------------------------------------------
        # 10. Return NaN must follow price NaN
        # -----------------------------------------------------

        checks[
            f"{horizon_name}_return_nan_pattern"
        ] = (
            actual_future_price.isna()
            .equals(
                actual_return.isna()
            )
        )

        # -----------------------------------------------------
        # 11. Future prices must be positive
        # -----------------------------------------------------

        valid_future_prices = (
            actual_future_price.dropna()
        )

        checks[
            f"{horizon_name}_positive_future_prices"
        ] = bool(
            (valid_future_prices > 0).all()
        )

        # -----------------------------------------------------
        # 12. No infinity in returns
        # -----------------------------------------------------

        checks[
            f"{horizon_name}_no_infinite_returns"
        ] = not np.isinf(
            actual_return.dropna()
        ).any()

        # -----------------------------------------------------
        # 13. Missing values must correspond to unavailable
        #     future timestamps.
        # -----------------------------------------------------

        missing_mask = (
            actual_future_price.isna()
        )

        missing_targets = (
            target_timestamp[
                missing_mask
            ]
        )

        if len(missing_targets) == 0:

            checks[
                f"{horizon_name}_missing_targets_valid"
            ] = True

        else:

            # Missing is allowed only when the exact future
            # open_time is not present in raw data.
            missing_exist_in_raw = (
                missing_targets.isin(
                    raw_lookup.index
                )
            )

            checks[
                f"{horizon_name}_missing_targets_valid"
            ] = not bool(
                missing_exist_in_raw.any()
            )

        # -----------------------------------------------------
        # Diagnostic counts
        # -----------------------------------------------------

        available_count = int(
            actual_future_price.notna().sum()
        )

        missing_count = int(
            actual_future_price.isna().sum()
        )

        checks[
            f"{horizon_name}_available_count"
        ] = available_count

        checks[
            f"{horizon_name}_missing_count"
        ] = missing_count

        if missing_count > 0:

            first_missing_target = (
                missing_targets.min()
            )

            last_missing_target = (
                missing_targets.max()
            )

            checks[
                f"{horizon_name}_first_missing_target"
            ] = str(first_missing_target)

            checks[
                f"{horizon_name}_last_missing_target"
            ] = str(last_missing_target)

        else:

            checks[
                f"{horizon_name}_first_missing_target"
            ] = ""

            checks[
                f"{horizon_name}_last_missing_target"
            ] = ""

    # ---------------------------------------------------------
    # Overall result
    # ---------------------------------------------------------

    validation_keys = [
        key
        for key, value in checks.items()
        if isinstance(value, (bool, np.bool_))
    ]

    checks["overall_pass"] = all(
        bool(checks[key])
        for key in validation_keys
    )

    print(
        "  RESULT:",
        "PASS"
        if checks["overall_pass"]
        else "FAIL",
    )

    return checks


def main():

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_rows = []

    overall_pass = True

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            checks = validate_dataset(
                symbol,
                timeframe,
            )

            row = {
                "symbol": symbol,
                "timeframe": timeframe,
                **checks,
            }

            report_rows.append(row)

            if not checks.get(
                "overall_pass",
                False,
            ):
                overall_pass = False

    report = pd.DataFrame(report_rows)

    output_file = (
        REPORT_DIR
        / "forward_returns_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    print("\n----------------------------------------")
    print("FORWARD RETURNS VALIDATION")
    print("----------------------------------------")

    display_columns = [
        "symbol",
        "timeframe",
        "overall_pass",
    ]

    print(
        report[
            display_columns
        ].to_string(index=False)
    )

    print("\nReport saved:")
    print(output_file)

    print("\nOVERALL RESULT:")

    if overall_pass:
        print("PASS")
    else:
        print("FAIL")


if __name__ == "__main__":
    main()