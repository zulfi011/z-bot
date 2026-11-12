from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")


STOP_LEVELS = {
    "1_0": 1.0,
    "1_5": 1.5,
    "2_0": 2.0,
    "2_5": 2.5,
    "3_0": 3.0,
}


VALID_OUTCOMES = [
    "target_first",
    "stop_first",
    "same_candle_ambiguous",
    "neither",
    "incomplete_unknown",
]


def calculate_statistics(
    symbol: str,
    timeframe: str,
) -> list[dict]:

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_first_hit.parquet"
        )
    )

    df = pd.read_parquet(input_file)

    rows = []

    # ---------------------------------------------------------
    # Group by the setup dimensions we actually care about.
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

        for stop_name, stop_pct in STOP_LEVELS.items():

            outcome_column = (
                f"target_2_5_vs_stop_{stop_name}_outcome"
            )

            outcomes = (
                group[
                    outcome_column
                ]
                .astype(str)
            )

            # -------------------------------------------------
            # Count every outcome type.
            # -------------------------------------------------

            counts = (
                outcomes
                .value_counts()
            )

            target_first_count = int(
                counts.get(
                    "target_first",
                    0,
                )
            )

            stop_first_count = int(
                counts.get(
                    "stop_first",
                    0,
                )
            )

            ambiguous_count = int(
                counts.get(
                    "same_candle_ambiguous",
                    0,
                )
            )

            neither_count = int(
                counts.get(
                    "neither",
                    0,
                )
            )

            incomplete_unknown_count = int(
                counts.get(
                    "incomplete_unknown",
                    0,
                )
            )

            total_event_rows = len(group)

            # -------------------------------------------------
            # Confirmed 24h outcome count.
            #
            # We exclude incomplete_unknown because the full
            # 24-hour result is not known.
            #
            # same_candle_ambiguous stays separate because with
            # 1-minute OHLC we cannot know ordering inside that
            # candle.
            # -------------------------------------------------

            confirmed_count = (
                target_first_count
                + stop_first_count
                + ambiguous_count
                + neither_count
            )

            # -------------------------------------------------
            # Probability among all confirmed outcomes.
            #
            # Answers:
            # "Of all events where the 24h result is known,
            #  what percentage had target first?"
            # -------------------------------------------------

            if confirmed_count > 0:

                target_first_pct_all_confirmed = (
                    target_first_count
                    / confirmed_count
                    * 100
                )

                stop_first_pct_all_confirmed = (
                    stop_first_count
                    / confirmed_count
                    * 100
                )

                neither_pct_all_confirmed = (
                    neither_count
                    / confirmed_count
                    * 100
                )

                ambiguous_pct_all_confirmed = (
                    ambiguous_count
                    / confirmed_count
                    * 100
                )

            else:

                target_first_pct_all_confirmed = None
                stop_first_pct_all_confirmed = None
                neither_pct_all_confirmed = None
                ambiguous_pct_all_confirmed = None

            # -------------------------------------------------
            # Decisive first-hit count.
            #
            # Only cases where target OR stop clearly happened
            # first.
            #
            # This excludes:
            # - neither
            # - ambiguous
            # - incomplete
            #
            # Answers:
            # "When one of the two levels was clearly hit first,
            #  how often was it the target?"
            # -------------------------------------------------

            decisive_count = (
                target_first_count
                + stop_first_count
            )

            if decisive_count > 0:

                target_first_pct_decisive = (
                    target_first_count
                    / decisive_count
                    * 100
                )

                stop_first_pct_decisive = (
                    stop_first_count
                    / decisive_count
                    * 100
                )

            else:

                target_first_pct_decisive = None
                stop_first_pct_decisive = None

            # -------------------------------------------------
            # Timing statistics for target-first and stop-first
            # outcomes.
            # -------------------------------------------------

            target_time_column = (
                "target_2_5_time_minutes"
            )

            stop_time_column = (
                f"stop_{stop_name}_time_minutes"
            )

            target_first_mask = (
                outcomes
                == "target_first"
            )

            stop_first_mask = (
                outcomes
                == "stop_first"
            )

            target_first_times = (
                group.loc[
                    target_first_mask,
                    target_time_column,
                ]
                .dropna()
                .astype(float)
            )

            stop_first_times = (
                group.loc[
                    stop_first_mask,
                    stop_time_column,
                ]
                .dropna()
                .astype(float)
            )

            if len(target_first_times) > 0:

                target_first_median_minutes = (
                    target_first_times.median()
                )

                target_first_mean_minutes = (
                    target_first_times.mean()
                )

                target_first_p25_minutes = (
                    target_first_times.quantile(
                        0.25
                    )
                )

                target_first_p75_minutes = (
                    target_first_times.quantile(
                        0.75
                    )
                )

            else:

                target_first_median_minutes = None
                target_first_mean_minutes = None
                target_first_p25_minutes = None
                target_first_p75_minutes = None

            if len(stop_first_times) > 0:

                stop_first_median_minutes = (
                    stop_first_times.median()
                )

                stop_first_mean_minutes = (
                    stop_first_times.mean()
                )

                stop_first_p25_minutes = (
                    stop_first_times.quantile(
                        0.25
                    )
                )

                stop_first_p75_minutes = (
                    stop_first_times.quantile(
                        0.75
                    )
                )

            else:

                stop_first_median_minutes = None
                stop_first_mean_minutes = None
                stop_first_p25_minutes = None
                stop_first_p75_minutes = None

            rows.append(
                {
                    "asset": symbol,
                    "timeframe": timeframe,
                    "average_type": average_type,
                    "touch_zone": touch_zone,

                    "target_pct": 2.5,

                    "stop_level": stop_name,
                    "stop_pct": stop_pct,

                    "total_event_rows": (
                        total_event_rows
                    ),

                    "confirmed_count": (
                        confirmed_count
                    ),

                    "decisive_count": (
                        decisive_count
                    ),

                    "target_first_count": (
                        target_first_count
                    ),

                    "stop_first_count": (
                        stop_first_count
                    ),

                    "same_candle_ambiguous_count": (
                        ambiguous_count
                    ),

                    "neither_count": (
                        neither_count
                    ),

                    "incomplete_unknown_count": (
                        incomplete_unknown_count
                    ),

                    "target_first_pct_all_confirmed": (
                        target_first_pct_all_confirmed
                    ),

                    "stop_first_pct_all_confirmed": (
                        stop_first_pct_all_confirmed
                    ),

                    "neither_pct_all_confirmed": (
                        neither_pct_all_confirmed
                    ),

                    "ambiguous_pct_all_confirmed": (
                        ambiguous_pct_all_confirmed
                    ),

                    "target_first_pct_decisive": (
                        target_first_pct_decisive
                    ),

                    "stop_first_pct_decisive": (
                        stop_first_pct_decisive
                    ),

                    "target_first_median_minutes": (
                        target_first_median_minutes
                    ),

                    "target_first_mean_minutes": (
                        target_first_mean_minutes
                    ),

                    "target_first_p25_minutes": (
                        target_first_p25_minutes
                    ),

                    "target_first_p75_minutes": (
                        target_first_p75_minutes
                    ),

                    "stop_first_median_minutes": (
                        stop_first_median_minutes
                    ),

                    "stop_first_mean_minutes": (
                        stop_first_mean_minutes
                    ),

                    "stop_first_p25_minutes": (
                        stop_first_p25_minutes
                    ),

                    "stop_first_p75_minutes": (
                        stop_first_p75_minutes
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
                f"Processing "
                f"{symbol} {timeframe}"
            )

            rows = calculate_statistics(
                symbol,
                timeframe,
            )

            all_rows.extend(
                rows
            )

    results = pd.DataFrame(
        all_rows
    )

    # ---------------------------------------------------------
    # Sort cleanly.
    # ---------------------------------------------------------

    results = (
        results
        .sort_values(
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "stop_pct",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    output_file = (
        RESULTS_DIR
        / "first_hit_statistics.csv"
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

    # ---------------------------------------------------------
    # Show our main candidate:
    # SOLUSDT / 15D / 0.5 zone
    # ---------------------------------------------------------

    candidate = results[
        (results["asset"] == "SOLUSDT")
        & (
            results["average_type"]
            == "15d"
        )
        & (
            results["touch_zone"]
            == 0.5
        )
    ].copy()

    display_columns = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",

        "target_pct",
        "stop_pct",

        "confirmed_count",

        "target_first_count",
        "stop_first_count",
        "neither_count",

        "target_first_pct_all_confirmed",
        "target_first_pct_decisive",

        "target_first_median_minutes",
        "stop_first_median_minutes",
    ]

    print(
        "\n"
        + "=" * 110
    )

    print(
        "SOLUSDT | 15D | 0.5% TOUCH ZONE"
    )

    print(
        "+2.5% TARGET VS STOP FIRST-HIT"
    )

    print(
        "=" * 110
    )

    print(
        candidate[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Also show best target-first decisive setups
    # for each stop level.
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 110
    )

    print(
        "TOP SETUPS BY TARGET-FIRST RATE"
    )

    print(
        "=" * 110
    )

    for stop_pct in sorted(
        results[
            "stop_pct"
        ].unique()
    ):

        print(
            f"\n+2.5% TARGET VS "
            f"-{stop_pct:g}% STOP"
        )

        subset = (
            results[
                results["stop_pct"]
                == stop_pct
            ]
            .sort_values(
                [
                    "target_first_pct_decisive",
                    "decisive_count",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(10)
        )

        print(
            subset[
                [
                    "asset",
                    "timeframe",
                    "average_type",
                    "touch_zone",
                    "decisive_count",
                    "target_first_pct_decisive",
                    "target_first_pct_all_confirmed",
                    "neither_pct_all_confirmed",
                    "target_first_median_minutes",
                    "stop_first_median_minutes",
                ]
            ].to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()