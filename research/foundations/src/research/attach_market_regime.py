from pathlib import Path

import numpy as np
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
RESULTS_DIR = Path("results/tables")


def classify_regime(df: pd.DataFrame) -> pd.Series:
    """
    Classify market regime using ONLY the ordering of the
    already-available 7D, 15D and 30D averages.

    Bullish:
        average_7d > average_15d > average_30d

    Bearish:
        average_7d < average_15d < average_30d

    Neutral:
        all other orderings, provided all averages exist.

    Missing:
        if any of the three averages is unavailable.
    """

    required_available = (
        df[
            [
                "average_7d",
                "average_15d",
                "average_30d",
            ]
        ]
        .notna()
        .all(axis=1)
    )

    bullish = (
        required_available
        & (
            df["average_7d"]
            > df["average_15d"]
        )
        & (
            df["average_15d"]
            > df["average_30d"]
        )
    )

    bearish = (
        required_available
        & (
            df["average_7d"]
            < df["average_15d"]
        )
        & (
            df["average_15d"]
            < df["average_30d"]
        )
    )

    regime = pd.Series(
        pd.NA,
        index=df.index,
        dtype="string",
    )

    regime.loc[
        required_available
    ] = "neutral"

    regime.loc[
        bullish
    ] = "bullish"

    regime.loc[
        bearish
    ] = "bearish"

    return regime


def process_file(
    symbol: str,
    timeframe: str,
):
    average_file = (
        PROCESSED_DIR
        / symbol
        / f"{symbol}_{timeframe}_with_averages.parquet"
    )

    event_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events.parquet"
    )

    output_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_regime.parquet"
    )

    if not average_file.exists():
        raise FileNotFoundError(
            f"Missing averages file: {average_file}"
        )

    if not event_file.exists():
        raise FileNotFoundError(
            f"Missing event file: {event_file}"
        )

    print(
        f"\nProcessing {symbol} {timeframe}"
    )

    # ---------------------------------------------------------
    # Load candle-level averages
    # ---------------------------------------------------------

    averages = pd.read_parquet(
        average_file,
        columns=[
            "open_time",
            "average_7d",
            "average_15d",
            "average_30d",
        ],
    )

    averages["open_time"] = pd.to_datetime(
        averages["open_time"],
        utc=True,
    )

    if averages[
        "open_time"
    ].duplicated().any():
        raise ValueError(
            f"{symbol} {timeframe}: "
            "duplicate open_time values in averages file"
        )

    averages[
        "market_regime"
    ] = classify_regime(
        averages
    )

    # ---------------------------------------------------------
    # Load touch events
    # ---------------------------------------------------------

    events = pd.read_parquet(
        event_file
    )

    events["timestamp"] = pd.to_datetime(
        events["timestamp"],
        utc=True,
    )

    original_rows = len(
        events
    )

    # ---------------------------------------------------------
    # Exact timestamp merge
    #
    # event timestamp represents the touch candle open_time.
    # No nearest timestamp matching.
    # ---------------------------------------------------------

    merged = events.merge(
        averages,
        left_on="timestamp",
        right_on="open_time",
        how="left",
        validate="many_to_one",
    )

    if len(
        merged
    ) != original_rows:
        raise ValueError(
            f"{symbol} {timeframe}: "
            "row count changed during regime merge"
        )

    # open_time duplicates timestamp after successful merge.
    merged = merged.drop(
        columns=[
            "open_time",
        ]
    )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    merged.to_parquet(
        output_file,
        index=False,
    )

    regime_counts = (
        merged[
            "market_regime"
        ]
        .value_counts(
            dropna=False
        )
    )

    print(
        f"Input events : {original_rows:,}"
    )

    print(
        f"Output events: {len(merged):,}"
    )

    print(
        "\nRegime counts:"
    )

    print(
        regime_counts.to_string()
    )

    return {
        "asset": symbol,
        "timeframe": timeframe,
        "event_count": len(
            merged
        ),
        "bullish_events": int(
            (
                merged[
                    "market_regime"
                ]
                == "bullish"
            ).sum()
        ),
        "neutral_events": int(
            (
                merged[
                    "market_regime"
                ]
                == "neutral"
            ).sum()
        ),
        "bearish_events": int(
            (
                merged[
                    "market_regime"
                ]
                == "bearish"
            ).sum()
        ),
        "unavailable_events": int(
            merged[
                "market_regime"
            ]
            .isna()
            .sum()
        ),
        "output_file": str(
            output_file
        ),
    }


def main():
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_rows = []

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            summary_rows.append(
                process_file(
                    symbol,
                    timeframe,
                )
            )

    summary = pd.DataFrame(
        summary_rows
    )

    classified = (
        summary[
            [
                "bullish_events",
                "neutral_events",
                "bearish_events",
            ]
        ]
        .sum(axis=1)
    )

    summary[
        "classified_events"
    ] = classified

    summary[
        "classified_pct"
    ] = (
        summary[
            "classified_events"
        ]
        / summary[
            "event_count"
        ]
        * 100
    )

    for regime in [
        "bullish",
        "neutral",
        "bearish",
    ]:
        summary[
            f"{regime}_pct"
        ] = (
            summary[
                f"{regime}_events"
            ]
            / summary[
                "classified_events"
            ]
            * 100
        )

    summary_file = (
        RESULTS_DIR
        / "market_regime_event_counts.csv"
    )

    summary.to_csv(
        summary_file,
        index=False,
    )

    print(
        "\n"
        + "=" * 110
    )

    print(
        "MARKET REGIME EVENT SUMMARY"
    )

    print(
        "=" * 110
    )

    print(
        summary[
            [
                "asset",
                "timeframe",
                "event_count",
                "bullish_events",
                "neutral_events",
                "bearish_events",
                "unavailable_events",
                "classified_pct",
                "bullish_pct",
                "neutral_pct",
                "bearish_pct",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        "\nSaved summary:"
    )

    print(
        summary_file
    )


if __name__ == "__main__":
    main()