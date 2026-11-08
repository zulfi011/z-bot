from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")


PROFIT_LEVELS = [
    "0_5",
    "1_0",
    "1_5",
    "2_0",
    "2_5",
    "3_0",
    "5_0",
]


def calculate_statistics(symbol: str, timeframe: str) -> list[dict]:

    input_file = (
        RESEARCH_DIR
        / symbol
        / f"{symbol}_{timeframe}_touch_events_with_profit_reach.parquet"
    )

    df = pd.read_parquet(input_file)

    rows = []

    # ---------------------------------------------------------
    # Group by the research dimensions we care about
    # ---------------------------------------------------------

    grouped = df.groupby(
        [
            "average_type",
            "touch_zone",
        ],
        dropna=False,
        sort=True,
    )

    for (
        average_type,
        touch_zone,
    ), group in grouped:

        for level in PROFIT_LEVELS:

            reached_column = (
                f"reached_{level}_pct"
            )

            time_column = (
                f"time_to_{level}_pct_minutes"
            )

            reached = (
                group[reached_column]
                .astype("boolean")
            )

            reached_count = int(
                (reached == True)
                .fillna(False)
                .sum()
            )

            not_reached_count = int(
                (reached == False)
                .fillna(False)
                .sum()
            )

            unknown_count = int(
                reached.isna().sum()
            )

            valid_event_count = (
                reached_count
                + not_reached_count
            )

            if valid_event_count > 0:

                reach_probability_pct = (
                    reached_count
                    / valid_event_count
                    * 100
                )

            else:

                reach_probability_pct = None

            # -------------------------------------------------
            # Timing statistics only for events that reached
            # the target.
            # -------------------------------------------------

            reached_times = (
                group.loc[
                    reached == True,
                    time_column,
                ]
                .dropna()
                .astype(float)
            )

            if len(reached_times) > 0:

                mean_time_minutes = (
                    reached_times.mean()
                )

                median_time_minutes = (
                    reached_times.median()
                )

                p25_time_minutes = (
                    reached_times.quantile(0.25)
                )

                p75_time_minutes = (
                    reached_times.quantile(0.75)
                )

                min_time_minutes = (
                    reached_times.min()
                )

                max_time_minutes = (
                    reached_times.max()
                )

            else:

                mean_time_minutes = None
                median_time_minutes = None
                p25_time_minutes = None
                p75_time_minutes = None
                min_time_minutes = None
                max_time_minutes = None

            rows.append(
                {
                    "asset": symbol,
                    "timeframe": timeframe,
                    "average_type": average_type,
                    "touch_zone": touch_zone,
                    "profit_level": level,

                    "total_event_rows": len(group),

                    "valid_event_count": valid_event_count,

                    "reached_count": reached_count,

                    "not_reached_count": not_reached_count,

                    "unknown_count": unknown_count,

                    "reach_probability_pct": (
                        reach_probability_pct
                    ),

                    "mean_time_minutes": (
                        mean_time_minutes
                    ),

                    "median_time_minutes": (
                        median_time_minutes
                    ),

                    "p25_time_minutes": (
                        p25_time_minutes
                    ),

                    "p75_time_minutes": (
                        p75_time_minutes
                    ),

                    "min_time_minutes": (
                        min_time_minutes
                    ),

                    "max_time_minutes": (
                        max_time_minutes
                    ),
                }
            )

    return rows


def main():

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    all_rows = []

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            print(
                f"Processing {symbol} {timeframe}"
            )

            rows = calculate_statistics(
                symbol,
                timeframe,
            )

            all_rows.extend(rows)

    results = pd.DataFrame(
        all_rows
    )

    # ---------------------------------------------------------
    # Add readable profit percentage
    # ---------------------------------------------------------

    level_map = {
        "0_5": 0.5,
        "1_0": 1.0,
        "1_5": 1.5,
        "2_0": 2.0,
        "2_5": 2.5,
        "3_0": 3.0,
        "5_0": 5.0,
    }

    results["profit_level_pct"] = (
        results["profit_level"]
        .map(level_map)
    )

    # Put readable percentage next to profit level
    column_order = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",

        "profit_level",
        "profit_level_pct",

        "total_event_rows",
        "valid_event_count",

        "reached_count",
        "not_reached_count",
        "unknown_count",

        "reach_probability_pct",

        "mean_time_minutes",
        "median_time_minutes",
        "p25_time_minutes",
        "p75_time_minutes",
        "min_time_minutes",
        "max_time_minutes",
    ]

    results = results[
        column_order
    ]

    results = results.sort_values(
        [
            "asset",
            "timeframe",
            "average_type",
            "touch_zone",
            "profit_level_pct",
        ]
    ).reset_index(drop=True)

    output_file = (
        RESULTS_DIR
        / "profit_reach_statistics.csv"
    )

    results.to_csv(
        output_file,
        index=False,
    )

    print("\nSaved:")
    print(output_file)

    print(
        f"\nTotal statistic rows: "
        f"{len(results):,}"
    )

    print(
        "\nSample results:\n"
    )

    print(
        results[
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "profit_level_pct",
                "valid_event_count",
                "reach_probability_pct",
                "median_time_minutes",
            ]
        ]
        .head(30)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()