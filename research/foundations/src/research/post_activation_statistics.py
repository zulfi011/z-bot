from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")


WINDOWS = [
    "1h",
    "4h",
    "24h",
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
            f"_touch_events_with_post_activation.parquet"
        )
    )

    df = pd.read_parquet(
        input_file
    )

    # ---------------------------------------------------------
    # Only events that actually reached +2.5%.
    # ---------------------------------------------------------

    activated = df[
        df[
            "trailing_activation_reached"
        ]
        == True
    ].copy()

    rows = []

    grouped = activated.groupby(
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

        for window in WINDOWS:

            complete_column = (
                f"post_activation_window_complete_{window}"
            )

            extra_upside_column = (
                f"extra_upside_after_activation_{window}_pct"
            )

            peak_time_column = (
                f"time_to_post_activation_peak_{window}_minutes"
            )

            retracement_available_column = (
                f"post_peak_retracement_available_{window}"
            )

            retracement_column = (
                f"max_retracement_from_peak_{window}_pct"
            )

            retracement_time_column = (
                f"time_from_peak_to_max_retracement_{window}_minutes"
            )

            # -------------------------------------------------
            # Complete activated windows only
            # -------------------------------------------------

            complete = (
                group[
                    complete_column
                ]
                .astype("boolean")
                .fillna(False)
            )

            complete_group = (
                group.loc[
                    complete
                ]
            )

            valid_count = len(
                complete_group
            )

            incomplete_count = (
                len(group)
                - valid_count
            )

            # -------------------------------------------------
            # Extra upside statistics
            # -------------------------------------------------

            extra_upside = (
                complete_group[
                    extra_upside_column
                ]
                .dropna()
                .astype(float)
            )

            peak_times = (
                complete_group[
                    peak_time_column
                ]
                .dropna()
                .astype(float)
            )

            if len(
                extra_upside
            ) > 0:

                mean_extra_upside = (
                    extra_upside.mean()
                )

                median_extra_upside = (
                    extra_upside.median()
                )

                p25_extra_upside = (
                    extra_upside.quantile(
                        0.25
                    )
                )

                p75_extra_upside = (
                    extra_upside.quantile(
                        0.75
                    )
                )

                p90_extra_upside = (
                    extra_upside.quantile(
                        0.90
                    )
                )

                p95_extra_upside = (
                    extra_upside.quantile(
                        0.95
                    )
                )

                max_extra_upside = (
                    extra_upside.max()
                )

            else:

                mean_extra_upside = None
                median_extra_upside = None
                p25_extra_upside = None
                p75_extra_upside = None
                p90_extra_upside = None
                p95_extra_upside = None
                max_extra_upside = None

            if len(
                peak_times
            ) > 0:

                median_time_to_peak = (
                    peak_times.median()
                )

                mean_time_to_peak = (
                    peak_times.mean()
                )

                p25_time_to_peak = (
                    peak_times.quantile(
                        0.25
                    )
                )

                p75_time_to_peak = (
                    peak_times.quantile(
                        0.75
                    )
                )

            else:

                median_time_to_peak = None
                mean_time_to_peak = None
                p25_time_to_peak = None
                p75_time_to_peak = None

            # -------------------------------------------------
            # Retracement statistics
            # -------------------------------------------------

            retracement_available = (
                complete_group[
                    retracement_available_column
                ]
                .astype("boolean")
                .fillna(False)
            )

            retracement_group = (
                complete_group.loc[
                    retracement_available
                ]
            )

            retracement_count = len(
                retracement_group
            )

            retracement = (
                retracement_group[
                    retracement_column
                ]
                .dropna()
                .astype(float)
            )

            retracement_times = (
                retracement_group[
                    retracement_time_column
                ]
                .dropna()
                .astype(float)
            )

            if len(
                retracement
            ) > 0:

                mean_retracement = (
                    retracement.mean()
                )

                median_retracement = (
                    retracement.median()
                )

                p25_retracement = (
                    retracement.quantile(
                        0.25
                    )
                )

                p75_retracement = (
                    retracement.quantile(
                        0.75
                    )
                )

                p90_severe_retracement = (
                    retracement.quantile(
                        0.10
                    )
                )

                p95_severe_retracement = (
                    retracement.quantile(
                        0.05
                    )
                )

                worst_retracement = (
                    retracement.min()
                )

            else:

                mean_retracement = None
                median_retracement = None
                p25_retracement = None
                p75_retracement = None
                p90_severe_retracement = None
                p95_severe_retracement = None
                worst_retracement = None

            if len(
                retracement_times
            ) > 0:

                median_time_to_retracement = (
                    retracement_times.median()
                )

                mean_time_to_retracement = (
                    retracement_times.mean()
                )

                p25_time_to_retracement = (
                    retracement_times.quantile(
                        0.25
                    )
                )

                p75_time_to_retracement = (
                    retracement_times.quantile(
                        0.75
                    )
                )

            else:

                median_time_to_retracement = None
                mean_time_to_retracement = None
                p25_time_to_retracement = None
                p75_time_to_retracement = None

            # -------------------------------------------------
            # Useful descriptive ratio
            #
            # Not a trading PnL metric.
            # -------------------------------------------------

            if (
                median_retracement is not None
                and median_retracement != 0
            ):

                median_extra_upside_to_retracement_ratio = (
                    median_extra_upside
                    / abs(
                        median_retracement
                    )
                )

            else:

                median_extra_upside_to_retracement_ratio = None

            rows.append(
                {
                    "asset": symbol,
                    "timeframe": timeframe,
                    "average_type": average_type,
                    "touch_zone": touch_zone,
                    "window": window,

                    "activated_event_rows": (
                        len(group)
                    ),

                    "complete_window_count": (
                        valid_count
                    ),

                    "incomplete_window_count": (
                        incomplete_count
                    ),

                    "retracement_measurable_count": (
                        retracement_count
                    ),

                    "mean_extra_upside_pct": (
                        mean_extra_upside
                    ),

                    "median_extra_upside_pct": (
                        median_extra_upside
                    ),

                    "p25_extra_upside_pct": (
                        p25_extra_upside
                    ),

                    "p75_extra_upside_pct": (
                        p75_extra_upside
                    ),

                    "p90_extra_upside_pct": (
                        p90_extra_upside
                    ),

                    "p95_extra_upside_pct": (
                        p95_extra_upside
                    ),

                    "max_extra_upside_pct": (
                        max_extra_upside
                    ),

                    "median_time_to_peak_minutes": (
                        median_time_to_peak
                    ),

                    "mean_time_to_peak_minutes": (
                        mean_time_to_peak
                    ),

                    "p25_time_to_peak_minutes": (
                        p25_time_to_peak
                    ),

                    "p75_time_to_peak_minutes": (
                        p75_time_to_peak
                    ),

                    "mean_retracement_pct": (
                        mean_retracement
                    ),

                    "median_retracement_pct": (
                        median_retracement
                    ),

                    "p25_retracement_pct": (
                        p25_retracement
                    ),

                    "p75_retracement_pct": (
                        p75_retracement
                    ),

                    "p90_severe_retracement_pct": (
                        p90_severe_retracement
                    ),

                    "p95_severe_retracement_pct": (
                        p95_severe_retracement
                    ),

                    "worst_retracement_pct": (
                        worst_retracement
                    ),

                    "median_time_to_retracement_minutes": (
                        median_time_to_retracement
                    ),

                    "mean_time_to_retracement_minutes": (
                        mean_time_to_retracement
                    ),

                    "p25_time_to_retracement_minutes": (
                        p25_time_to_retracement
                    ),

                    "p75_time_to_retracement_minutes": (
                        p75_time_to_retracement
                    ),

                    "median_extra_upside_to_retracement_ratio": (
                        median_extra_upside_to_retracement_ratio
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

    window_order = {
        "1h": 1,
        "4h": 2,
        "24h": 3,
    }

    results[
        "_window_order"
    ] = (
        results["window"]
        .map(
            window_order
        )
    )

    results = (
        results
        .sort_values(
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "_window_order",
            ]
        )
        .drop(
            columns=[
                "_window_order"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    output_file = (
        RESULTS_DIR
        / "post_activation_statistics.csv"
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
    # Main candidate
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
    ]

    print(
        "\n"
        + "=" * 110
    )

    print(
        "SOLUSDT | 15D | 0.5% TOUCH ZONE"
    )

    print(
        "POST +2.5% ACTIVATION BEHAVIOR"
    )

    print(
        "=" * 110
    )

    display_columns = [
        "asset",
        "timeframe",
        "window",

        "activated_event_rows",

        "median_extra_upside_pct",
        "p75_extra_upside_pct",
        "p90_extra_upside_pct",

        "median_time_to_peak_minutes",

        "median_retracement_pct",
        "p90_severe_retracement_pct",

        "median_time_to_retracement_minutes",

        "median_extra_upside_to_retracement_ratio",
    ]

    print(
        candidate[
            display_columns
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()