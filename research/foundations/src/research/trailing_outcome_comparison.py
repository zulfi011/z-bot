from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")


TRAIL_LEVELS = [
    "10",
    "20",
    "30",
    "40",
    "50",
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
            f"_touch_events_with_trailing_research.parquet"
        )
    )

    df = pd.read_parquet(
        input_file
    )

    # ---------------------------------------------------------
    # Only events that reached +2.5%
    # ---------------------------------------------------------

    activated = df[
        df[
            "trailing_activation_reached"
        ]
        .fillna(False)
        .astype(bool)
    ].copy()

    rows = []

    grouped = activated.groupby(
        [
            "average_type",
            "touch_zone",
        ],
        sort=True,
        dropna=False,
    )

    for (
        average_type,
        touch_zone,
    ), group in grouped:

        for trail in TRAIL_LEVELS:

            outcome_column = (
                f"trail_{trail}_outcome"
            )

            trail_price_column = (
                f"trail_{trail}_old_trail_price"
            )

            locked_profit_column = (
                f"trail_{trail}_old_locked_profit_pct"
            )

            event_time_column = (
                f"trail_{trail}_time_minutes"
            )

            outcomes = (
                group[
                    outcome_column
                ]
                .astype("string")
            )

            # -------------------------------------------------
            # Outcome counts
            # -------------------------------------------------

            counts = (
                outcomes
                .value_counts()
            )

            resolved_count = int(
                counts.get(
                    "triggered_resolved",
                    0,
                )
            )

            ambiguous_count = int(
                counts.get(
                    "ambiguous_same_candle",
                    0,
                )
            )

            not_triggered_count = int(
                counts.get(
                    "not_triggered_24h",
                    0,
                )
            )

            incomplete_count = int(
                counts.get(
                    "incomplete_unknown",
                    0,
                )
            )

            confirmed_count = (
                resolved_count
                + ambiguous_count
                + not_triggered_count
            )

            # -------------------------------------------------
            # Resolved trailing exits
            #
            # For a resolved hit, the old trail price existed
            # before the candle opened.
            #
            # We therefore use the old trail price as the
            # theoretical exit threshold.
            # -------------------------------------------------

            resolved_mask = (
                outcomes
                == "triggered_resolved"
            )

            resolved_group = (
                group.loc[
                    resolved_mask
                ]
            )

            realized_returns = (
                resolved_group[
                    locked_profit_column
                ]
                .dropna()
                .astype(float)
            )

            event_times = (
                resolved_group[
                    event_time_column
                ]
                .dropna()
                .astype(float)
            )

            # -------------------------------------------------
            # Realized return statistics
            # -------------------------------------------------

            if len(
                realized_returns
            ) > 0:

                mean_realized_return = (
                    realized_returns.mean()
                )

                median_realized_return = (
                    realized_returns.median()
                )

                p10_realized_return = (
                    realized_returns.quantile(
                        0.10
                    )
                )

                p25_realized_return = (
                    realized_returns.quantile(
                        0.25
                    )
                )

                p75_realized_return = (
                    realized_returns.quantile(
                        0.75
                    )
                )

                p90_realized_return = (
                    realized_returns.quantile(
                        0.90
                    )
                )

                min_realized_return = (
                    realized_returns.min()
                )

                max_realized_return = (
                    realized_returns.max()
                )

            else:

                mean_realized_return = None
                median_realized_return = None
                p10_realized_return = None
                p25_realized_return = None
                p75_realized_return = None
                p90_realized_return = None
                min_realized_return = None
                max_realized_return = None

            # -------------------------------------------------
            # Time statistics
            # -------------------------------------------------

            if len(
                event_times
            ) > 0:

                median_time_to_exit = (
                    event_times.median()
                )

                mean_time_to_exit = (
                    event_times.mean()
                )

                p25_time_to_exit = (
                    event_times.quantile(
                        0.25
                    )
                )

                p75_time_to_exit = (
                    event_times.quantile(
                        0.75
                    )
                )

            else:

                median_time_to_exit = None
                mean_time_to_exit = None
                p25_time_to_exit = None
                p75_time_to_exit = None

            # -------------------------------------------------
            # Percentages
            # -------------------------------------------------

            if confirmed_count > 0:

                resolved_pct = (
                    resolved_count
                    / confirmed_count
                    * 100
                )

                ambiguous_pct = (
                    ambiguous_count
                    / confirmed_count
                    * 100
                )

                not_triggered_pct = (
                    not_triggered_count
                    / confirmed_count
                    * 100
                )

            else:

                resolved_pct = None
                ambiguous_pct = None
                not_triggered_pct = None

            rows.append(
                {
                    "asset": symbol,
                    "timeframe": timeframe,
                    "average_type": average_type,
                    "touch_zone": touch_zone,

                    "trail_giveback_pct": float(
                        trail
                    ),

                    "activated_event_rows": (
                        len(group)
                    ),

                    "confirmed_count": (
                        confirmed_count
                    ),

                    "resolved_count": (
                        resolved_count
                    ),

                    "ambiguous_count": (
                        ambiguous_count
                    ),

                    "not_triggered_24h_count": (
                        not_triggered_count
                    ),

                    "incomplete_unknown_count": (
                        incomplete_count
                    ),

                    "resolved_pct_confirmed": (
                        resolved_pct
                    ),

                    "ambiguous_pct_confirmed": (
                        ambiguous_pct
                    ),

                    "not_triggered_pct_confirmed": (
                        not_triggered_pct
                    ),

                    "mean_realized_return_pct": (
                        mean_realized_return
                    ),

                    "median_realized_return_pct": (
                        median_realized_return
                    ),

                    "p10_realized_return_pct": (
                        p10_realized_return
                    ),

                    "p25_realized_return_pct": (
                        p25_realized_return
                    ),

                    "p75_realized_return_pct": (
                        p75_realized_return
                    ),

                    "p90_realized_return_pct": (
                        p90_realized_return
                    ),

                    "min_realized_return_pct": (
                        min_realized_return
                    ),

                    "max_realized_return_pct": (
                        max_realized_return
                    ),

                    "median_time_to_exit_minutes": (
                        median_time_to_exit
                    ),

                    "mean_time_to_exit_minutes": (
                        mean_time_to_exit
                    ),

                    "p25_time_to_exit_minutes": (
                        p25_time_to_exit
                    ),

                    "p75_time_to_exit_minutes": (
                        p75_time_to_exit
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

    results = (
        results
        .sort_values(
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "trail_giveback_pct",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    output_file = (
        RESULTS_DIR
        / "trailing_outcome_comparison.csv"
    )

    results.to_csv(
        output_file,
        index=False,
    )

    print("\nSaved:")
    print(output_file)

    print(
        f"\nTotal rows: "
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
        + "=" * 120
    )

    print(
        "SOLUSDT | 15D | 0.5% TOUCH ZONE"
    )

    print(
        "TRAILING OUTCOME COMPARISON"
    )

    print(
        "=" * 120
    )

    display_columns = [
        "asset",
        "timeframe",
        "trail_giveback_pct",

        "activated_event_rows",

        "resolved_pct_confirmed",
        "ambiguous_pct_confirmed",
        "not_triggered_pct_confirmed",

        "median_realized_return_pct",
        "mean_realized_return_pct",

        "p25_realized_return_pct",
        "p75_realized_return_pct",

        "median_time_to_exit_minutes",
    ]

    print(
        candidate[
            display_columns
        ].to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Ranking by median realized return
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 120
    )

    print(
        "BEST TRAILS BY MEDIAN REALIZED RETURN"
    )

    print(
        "=" * 120
    )

    ranked = (
        results[
            results[
                "resolved_count"
            ]
            >= 1000
        ]
        .sort_values(
            [
                "median_realized_return_pct",
                "resolved_count",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .head(30)
    )

    print(
        ranked[
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "trail_giveback_pct",
                "resolved_count",
                "median_realized_return_pct",
                "mean_realized_return_pct",
                "ambiguous_pct_confirmed",
                "median_time_to_exit_minutes",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()