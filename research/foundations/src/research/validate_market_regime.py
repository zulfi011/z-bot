from pathlib import Path

import pandas as pd


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

TIMEFRAMES = [
    "1m",
    "3m",
    "5m",
]

PROCESSED_DIR = Path("data/processed")
RESEARCH_DIR = Path("data/research")
REPORT_DIR = Path("results/reports")


def expected_regime(row):
    a7 = row["average_7d"]
    a15 = row["average_15d"]
    a30 = row["average_30d"]

    if pd.isna(a7) or pd.isna(a15) or pd.isna(a30):
        return pd.NA

    if a7 > a15 > a30:
        return "bullish"

    if a7 < a15 < a30:
        return "bearish"

    return "neutral"


def validate_file(
    symbol: str,
    timeframe: str,
):
    averages_file = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_averages.parquet"
    )

    source_events_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events.parquet"
    )

    regime_events_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_regime.parquet"
    )

    averages = pd.read_parquet(
        averages_file,
        columns=[
            "open_time",
            "average_7d",
            "average_15d",
            "average_30d",
        ],
    )

    source = pd.read_parquet(
        source_events_file
    )

    actual = pd.read_parquet(
        regime_events_file
    )

    averages["open_time"] = pd.to_datetime(
        averages["open_time"],
        utc=True,
    )

    source["timestamp"] = pd.to_datetime(
        source["timestamp"],
        utc=True,
    )

    actual["timestamp"] = pd.to_datetime(
        actual["timestamp"],
        utc=True,
    )

    checks = {}

    # ---------------------------------------------------------
    # Row preservation
    # ---------------------------------------------------------

    checks["row_count_preserved"] = (
        len(source)
        == len(actual)
    )

    # ---------------------------------------------------------
    # Event identity preserved
    # ---------------------------------------------------------

    checks["event_ids_preserved"] = (
        source["event_id"]
        .astype(str)
        .reset_index(drop=True)
        .equals(
            actual["event_id"]
            .astype(str)
            .reset_index(drop=True)
        )
    )

    checks["timestamps_preserved"] = (
        source["timestamp"]
        .reset_index(drop=True)
        .equals(
            actual["timestamp"]
            .reset_index(drop=True)
        )
    )

    # ---------------------------------------------------------
    # Exact timestamp lookup
    # ---------------------------------------------------------

    expected = source[
        [
            "event_id",
            "timestamp",
        ]
    ].merge(
        averages,
        left_on="timestamp",
        right_on="open_time",
        how="left",
        validate="many_to_one",
    )

    expected[
        "expected_regime"
    ] = expected.apply(
        expected_regime,
        axis=1,
    )

    comparison = actual[
        [
            "event_id",
            "market_regime",
        ]
    ].merge(
        expected[
            [
                "event_id",
                "average_7d",
                "average_15d",
                "average_30d",
                "expected_regime",
            ]
        ],
        on="event_id",
        how="left",
        validate="one_to_one",
    )

    # ---------------------------------------------------------
    # Classification correctness
    # ---------------------------------------------------------

    actual_regime = (
        comparison["market_regime"]
        .astype("string")
    )

    expected_regime_series = (
        comparison["expected_regime"]
        .astype("string")
    )

    checks["regime_classification_correct"] = (
        actual_regime.fillna("__NA__")
        .equals(
            expected_regime_series.fillna("__NA__")
        )
    )

    # ---------------------------------------------------------
    # Bullish correctness
    # ---------------------------------------------------------

    bullish_rows = comparison[
        comparison["market_regime"]
        == "bullish"
    ]

    checks["all_bullish_order_correct"] = (
        (
            bullish_rows["average_7d"]
            > bullish_rows["average_15d"]
        )
        &
        (
            bullish_rows["average_15d"]
            > bullish_rows["average_30d"]
        )
    ).all()

    # ---------------------------------------------------------
    # Bearish correctness
    # ---------------------------------------------------------

    bearish_rows = comparison[
        comparison["market_regime"]
        == "bearish"
    ]

    checks["all_bearish_order_correct"] = (
        (
            bearish_rows["average_7d"]
            < bearish_rows["average_15d"]
        )
        &
        (
            bearish_rows["average_15d"]
            < bearish_rows["average_30d"]
        )
    ).all()

    # ---------------------------------------------------------
    # Neutral correctness
    # ---------------------------------------------------------

    neutral_rows = comparison[
        comparison["market_regime"]
        == "neutral"
    ]

    neutral_bullish = (
        (
            neutral_rows["average_7d"]
            > neutral_rows["average_15d"]
        )
        &
        (
            neutral_rows["average_15d"]
            > neutral_rows["average_30d"]
        )
    )

    neutral_bearish = (
        (
            neutral_rows["average_7d"]
            < neutral_rows["average_15d"]
        )
        &
        (
            neutral_rows["average_15d"]
            < neutral_rows["average_30d"]
        )
    )

    checks["neutral_is_neither_bullish_nor_bearish"] = (
        (~neutral_bullish & ~neutral_bearish).all()
    )

    checks["neutral_has_all_averages"] = (
        neutral_rows[
            [
                "average_7d",
                "average_15d",
                "average_30d",
            ]
        ]
        .notna()
        .all(axis=1)
        .all()
    )

    # ---------------------------------------------------------
    # Missing regime only when averages unavailable
    # ---------------------------------------------------------

    missing_rows = comparison[
        comparison["market_regime"]
        .isna()
    ]

    checks["missing_regime_due_to_missing_average"] = (
        missing_rows[
            [
                "average_7d",
                "average_15d",
                "average_30d",
            ]
        ]
        .isna()
        .any(axis=1)
        .all()
    )

    # ---------------------------------------------------------
    # Same timestamp must always have same regime
    # ---------------------------------------------------------

    timestamp_regime_count = (
        actual
        .groupby(
            "timestamp",
            dropna=False,
        )["market_regime"]
        .nunique(
            dropna=False
        )
    )

    checks["one_regime_per_timestamp"] = (
        timestamp_regime_count.max()
        == 1
    )

    # ---------------------------------------------------------
    # Allowed labels only
    # ---------------------------------------------------------

    allowed = {
        "bullish",
        "neutral",
        "bearish",
    }

    actual_labels = set(
        actual[
            "market_regime"
        ]
        .dropna()
        .unique()
    )

    checks["only_allowed_regime_labels"] = (
        actual_labels
        <= allowed
    )

    return checks


def main():
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:

            print(
                f"Validating {symbol} {timeframe}"
            )

            checks = validate_file(
                symbol,
                timeframe,
            )

            for check_name, passed in checks.items():
                rows.append(
                    {
                        "asset": symbol,
                        "timeframe": timeframe,
                        "check": check_name,
                        "pass": bool(passed),
                    }
                )

    report = pd.DataFrame(
        rows
    )

    report_file = (
        REPORT_DIR
        / "market_regime_validation.csv"
    )

    report.to_csv(
        report_file,
        index=False,
    )

    failed = report[
        report["pass"]
        == False
    ]

    print(
        "\n"
        + "=" * 90
    )

    print(
        "MARKET REGIME VALIDATION"
    )

    print(
        "=" * 90
    )

    if len(failed) == 0:
        print(
            "ALL CHECKS PASS"
        )
    else:
        print(
            "FAILED CHECKS:"
        )

        print(
            failed.to_string(
                index=False
            )
        )

    print(
        "\nChecks:",
        len(report),
    )

    print(
        "Passed:",
        int(
            report["pass"].sum()
        ),
    )

    print(
        "Failed:",
        int(
            (~report["pass"]).sum()
        ),
    )

    print(
        "\nReport saved:"
    )

    print(
        report_file
    )


if __name__ == "__main__":
    main()