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


REQUIRED_EVENT_COLUMNS = [
    "event_id",
    "touch_group_id",
    "asset",
    "timeframe",
    "timestamp",
    "average_type",
    "average_value",
    "price",
    "high",
    "low",
    "distance_pct",
    "touch_zone",
]


def get_touch_source_path(symbol, timeframe):
    return Path(
        f"data/processed/"
        f"{symbol}/"
        f"{symbol}_{timeframe}_with_touches.parquet"
    )


def get_event_path(symbol, timeframe):
    return Path(
        f"data/research/"
        f"{symbol}/"
        f"{symbol}_{timeframe}_touch_events.parquet"
    )


def validate_dataset(symbol, timeframe):
    source_path = get_touch_source_path(symbol, timeframe)
    event_path = get_event_path(symbol, timeframe)

    source = pd.read_parquet(source_path)
    events = pd.read_parquet(event_path)

    checks = {}

    # =========================================================
    # 1. Output file exists
    # =========================================================
    checks["event_file_exists"] = event_path.exists()

    if not checks["event_file_exists"]:
        raise FileNotFoundError(
            f"Missing event file: {event_path}"
        )

    # =========================================================
    # 2. Required columns
    # =========================================================
    checks["required_columns_present"] = all(
        column in events.columns
        for column in REQUIRED_EVENT_COLUMNS
    )

    # =========================================================
    # 3. Expected asset and timeframe
    # =========================================================
    checks["asset_correct"] = (
        events["asset"].eq(symbol).all()
    )

    checks["timeframe_correct"] = (
        events["timeframe"].eq(timeframe).all()
    )

    # =========================================================
    # 4. Valid average types
    # =========================================================
    checks["average_types_valid"] = (
        events["average_type"]
        .isin(AVERAGES.keys())
        .all()
    )

    # =========================================================
    # 5. Valid touch zones
    # =========================================================
    expected_zones = {
        0.5,
        1.0,
        1.5,
    }

    checks["touch_zones_valid"] = (
        set(events["touch_zone"].unique())
        .issubset(expected_zones)
    )

    # =========================================================
    # 6. Timestamp validation
    # =========================================================
    checks["timestamps_utc"] = (
        isinstance(
            events["timestamp"].dtype,
            pd.DatetimeTZDtype,
        )
        and str(events["timestamp"].dt.tz) == "UTC"
    )

    checks["timestamps_sorted"] = (
        events["timestamp"].is_monotonic_increasing
    )

    # =========================================================
    # 7. No duplicate event IDs
    # =========================================================
    checks["duplicate_event_ids"] = (
        events["event_id"].duplicated().sum() == 0
    )

    # =========================================================
    # 8. No missing critical values
    # =========================================================
    critical_columns = [
        "event_id",
        "touch_group_id",
        "asset",
        "timeframe",
        "timestamp",
        "average_type",
        "average_value",
        "price",
        "high",
        "low",
        "distance_pct",
        "touch_zone",
    ]

    checks["no_missing_values"] = (
        not events[critical_columns].isna().any().any()
    )

    # =========================================================
    # 9. Price must be positive
    # =========================================================
    checks["positive_prices"] = (
        (events["price"] > 0).all()
        and (events["average_value"] > 0).all()
    )

    # =========================================================
    # 10. OHLC consistency
    # =========================================================
    checks["ohlc_consistent"] = (
        (events["high"] >= events["low"]).all()
        and (events["price"] <= events["high"]).all()
        and (events["price"] >= events["low"]).all()
    )

    # =========================================================
    # 11. Distance calculation
    # =========================================================
    expected_distance = (
        (
            events["price"]
            - events["average_value"]
        )
        / events["average_value"]
        * 100
    )

    distance_matches = (
        events["distance_pct"]
        .sub(expected_distance)
        .abs()
        < 1e-10
    )

    checks["distance_calculation_correct"] = (
        distance_matches.all()
    )

    # =========================================================
    # 12. Verify every event against original touch flags
    # =========================================================
    source_lookup = source[
        [
            "open_time",
            "average_7d",
            "average_15d",
            "average_30d",
        ]
        + [
            f"touch_{average_name}_{zone_name}"
            for average_name in AVERAGES
            for zone_name in ZONES
        ]
    ].copy()

    source_lookup = source_lookup.rename(
        columns={"open_time": "timestamp"}
    )

    merged = events.merge(
        source_lookup,
        on="timestamp",
        how="left",
        validate="many_to_one",
    )

    # Make sure every event timestamp exists in source.
    checks["all_event_timestamps_found"] = (
        merged["average_7d"].notna()
        | merged["average_15d"].notna()
        | merged["average_30d"].notna()
    ).all()

    # =========================================================
    # 13. Verify average value matches source
    # =========================================================
    average_value_correct = True

    for average_name, average_column in AVERAGES.items():

        mask = merged["average_type"] == average_name

        if mask.any():

            difference = (
                merged.loc[mask, "average_value"]
                - merged.loc[mask, average_column]
            ).abs()

            if not (difference < 1e-10).all():
                average_value_correct = False

    checks["average_values_correct"] = average_value_correct

    # =========================================================
    # 14. Verify price against original candle close
    # =========================================================
    source_prices = source[
        ["open_time", "close"]
    ].rename(
        columns={"open_time": "timestamp"}
    )

    merged_price = events.merge(
        source_prices,
        on="timestamp",
        how="left",
        validate="many_to_one",
    )

    price_difference = (
        merged_price["price"]
        - merged_price["close"]
    ).abs()

    checks["price_matches_source_close"] = (
        price_difference < 1e-10
    ).all()

    # =========================================================
    # 15. Verify high/low against original candle
    # =========================================================
    source_ohlc = source[
        ["open_time", "high", "low"]
    ].rename(
        columns={"open_time": "timestamp"}
    )

    merged_ohlc = events.merge(
        source_ohlc,
        on="timestamp",
        how="left",
        validate="many_to_one",
        suffixes=("_event", "_source"),
    )

    high_difference = (
        merged_ohlc["high_event"]
        - merged_ohlc["high_source"]
    ).abs()

    low_difference = (
        merged_ohlc["low_event"]
        - merged_ohlc["low_source"]
    ).abs()

    checks["high_matches_source"] = (
        high_difference < 1e-10
    ).all()

    checks["low_matches_source"] = (
        low_difference < 1e-10
    ).all()

    # =========================================================
    # 16. Verify the actual touch flag is TRUE
    # =========================================================
    touch_flag_correct = True

    for average_name in AVERAGES:
        for zone_name in ZONES:

            mask = (
                (events["average_type"] == average_name)
                & (
                    events["touch_zone"]
                    == ZONES[zone_name] * 100
                )
            )

            if not mask.any():
                continue

            touch_column = (
                f"touch_{average_name}_{zone_name}"
            )

            source_touch_lookup = source[
                ["open_time", touch_column]
            ].rename(
                columns={"open_time": "timestamp"}
            )

            event_subset = events.loc[
                mask,
                ["timestamp"]
            ].merge(
                source_touch_lookup,
                on="timestamp",
                how="left",
                validate="many_to_one",
            )

            if not event_subset[touch_column].eq(True).all():
                touch_flag_correct = False

    checks["all_events_are_real_touches"] = (
        touch_flag_correct
    )

    # =========================================================
    # 17. 81 count reconciliation checks
    # =========================================================
    count_checks_pass = True

    for average_name in AVERAGES:

        for zone_name in ZONES:

            touch_column = (
                f"touch_{average_name}_{zone_name}"
            )

            source_count = int(
                source[touch_column].sum()
            )

            event_count = int(
                (
                    (events["average_type"] == average_name)
                    & (
                        events["touch_zone"]
                        == ZONES[zone_name] * 100
                    )
                ).sum()
            )

            if source_count != event_count:
                count_checks_pass = False

    checks["all_touch_counts_match"] = (
        count_checks_pass
    )

    # =========================================================
    # 18. Verify touch_group_id uniqueness definition
    #
    # A group should represent:
    # asset + timeframe + timestamp + average_type
    # =========================================================
    expected_group_id = (
        events["asset"].astype(str)
        + "_"
        + events["timeframe"].astype(str)
        + "_"
        + events["timestamp"].astype(str)
        + "_"
        + events["average_type"].astype(str)
    )

    checks["touch_group_ids_correct"] = (
        events["touch_group_id"]
        .eq(expected_group_id)
        .all()
    )

    # =========================================================
    # 19. Verify event_id uniqueness definition
    # =========================================================
    expected_event_id = (
        events["touch_group_id"].astype(str)
        + "_"
        + events["touch_zone"].astype(str)
        + "pct"
    )

    checks["event_ids_correct"] = (
        events["event_id"]
        .eq(expected_event_id)
        .all()
    )

    # =========================================================
    # Overall result
    # =========================================================
    checks["overall_pass"] = all(checks.values())

    return checks


def main():

    print("=" * 70)
    print("TOUCH EVENT VALIDATION")
    print("=" * 70)

    results = []

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:

            print(
                f"\nValidating {symbol} {timeframe}..."
            )

            checks = validate_dataset(
                symbol,
                timeframe,
            )

            row = {
                "symbol": symbol,
                "timeframe": timeframe,
                **checks,
            }

            results.append(row)

            status = (
                "PASS"
                if checks["overall_pass"]
                else "FAIL"
            )

            print(f"  {status}")

    results_df = pd.DataFrame(results)

    output_path = Path(
        "results/reports/touch_event_validation.csv"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_df.to_csv(
        output_path,
        index=False,
    )

    print()
    print("=" * 70)
    print("VALIDATION RESULTS")
    print("=" * 70)

    print(
        results_df.to_string(index=False)
    )

    print()
    print(
        f"Report saved to: {output_path}"
    )

    print()

    if results_df["overall_pass"].all():
        print("OVERALL RESULT: PASS")
    else:
        print("OVERALL RESULT: FAIL")


if __name__ == "__main__":
    main()
