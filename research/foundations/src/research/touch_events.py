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
        f"data/processed/{symbol}/{symbol}_{timeframe}_with_touches.parquet"
    )


def get_output_path(symbol, timeframe):
    return Path(
        f"data/research/{symbol}/{symbol}_{timeframe}_touch_events.parquet"
    )


def generate_touch_events(symbol, timeframe):
    input_path = get_input_path(symbol, timeframe)
    output_path = get_output_path(symbol, timeframe)

    df = pd.read_parquet(input_path)

    required_columns = [
        "open_time",
        "high",
        "low",
        "close",
    ]

    for average_column in AVERAGES.values():
        required_columns.append(average_column)

    for average_name in AVERAGES:
        for zone_name in ZONES:
            required_columns.append(
                f"touch_{average_name}_{zone_name}"
            )

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{symbol} {timeframe}: missing columns: {missing_columns}"
        )

    events = []

    for average_name, average_column in AVERAGES.items():

        for zone_name, zone_percentage in ZONES.items():

            touch_column = f"touch_{average_name}_{zone_name}"

            touched = df[touch_column]

            if not touched.any():
                continue

            touched_rows = df.loc[touched].copy()

            events_for_zone = pd.DataFrame(
                {
                    "asset": symbol,
                    "timeframe": timeframe,
                    "timestamp": touched_rows["open_time"],
                    "average_type": average_name,
                    "average_value": touched_rows[average_column],
                    "price": touched_rows["close"],
                    "high": touched_rows["high"],
                    "low": touched_rows["low"],
                    "distance_pct": (
                        (
                            touched_rows["close"]
                            - touched_rows[average_column]
                        )
                        / touched_rows[average_column]
                        * 100
                    ),
                    "touch_zone": zone_percentage * 100,
                }
            )

            events.append(events_for_zone)

    if not events:
        raise ValueError(
            f"{symbol} {timeframe}: no touch events found."
        )

    events_df = pd.concat(
        events,
        ignore_index=True,
    )

    # ---------------------------------------------------------
    # Create a stable identifier for the underlying
    # candle + average touch occurrence.
    #
    # Multiple zone rows can belong to the same group because
    # the zones are nested.
    # ---------------------------------------------------------
    events_df["touch_group_id"] = (
        events_df["asset"].astype(str)
        + "_"
        + events_df["timeframe"].astype(str)
        + "_"
        + events_df["timestamp"].astype(str)
        + "_"
        + events_df["average_type"].astype(str)
    )

    # ---------------------------------------------------------
    # Each row represents one zone classification.
    # ---------------------------------------------------------
    events_df["event_id"] = (
        events_df["touch_group_id"]
        + "_"
        + events_df["touch_zone"].astype(str)
        + "pct"
    )

    # ---------------------------------------------------------
    # Ensure correct timestamp type and ordering.
    # ---------------------------------------------------------
    events_df["timestamp"] = pd.to_datetime(
        events_df["timestamp"],
        utc=True,
    )

    events_df = events_df.sort_values(
        [
            "timestamp",
            "average_type",
            "touch_zone",
        ]
    ).reset_index(drop=True)

    # ---------------------------------------------------------
    # Explicit column order.
    # ---------------------------------------------------------
    events_df = events_df[
        [
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
    ]

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    events_df.to_parquet(
        output_path,
        index=False,
    )

    return events_df


def main():
    print("=" * 70)
    print("GENERATING TOUCH EVENTS")
    print("=" * 70)

    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:

            print(
                f"\nGenerating {symbol} {timeframe}..."
            )

            events_df = generate_touch_events(
                symbol,
                timeframe,
            )

            print(
                f"  Touch event rows: {len(events_df):,}"
            )

            print(
                f"  Touch groups: "
                f"{events_df['touch_group_id'].nunique():,}"
            )

            print(
                f"  Output: "
                f"data/research/{symbol}/"
                f"{symbol}_{timeframe}_touch_events.parquet"
            )

    print("\n" + "=" * 70)
    print("TOUCH EVENT GENERATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
