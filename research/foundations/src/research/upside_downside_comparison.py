from pathlib import Path

import pandas as pd


PROFIT_FILE = Path(
    "results/tables/profit_reach_statistics.csv"
)

DOWNSIDE_FILE = Path(
    "results/tables/downside_statistics.csv"
)

OUTPUT_FILE = Path(
    "results/tables/upside_downside_comparison.csv"
)


def main():

    profit = pd.read_csv(PROFIT_FILE)
    downside = pd.read_csv(DOWNSIDE_FILE)

    # ---------------------------------------------------------
    # We care mainly about the 24h downside because Part 13
    # profit reach was also measured over a 24h observation.
    # ---------------------------------------------------------

    downside_24h = downside[
        downside["window"] == "24h"
    ].copy()

    # ---------------------------------------------------------
    # Merge on the exact same research setup
    # ---------------------------------------------------------

    combined = profit.merge(
        downside_24h[
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "valid_event_count",
                "median_downside_pct",
                "p90_severe_downside_pct",
                "p95_severe_downside_pct",
                "worst_downside_pct",
            ]
        ],
        on=[
            "asset",
            "timeframe",
            "average_type",
            "touch_zone",
        ],
        how="left",
        suffixes=(
            "_profit",
            "_downside",
        ),
        validate="many_to_one",
    )

    # ---------------------------------------------------------
    # Simple descriptive ratios.
    #
    # These are NOT profitability metrics yet.
    # They only help compare upside target size versus typical
    # downside severity.
    # ---------------------------------------------------------

    combined[
        "target_to_median_downside_ratio"
    ] = (
        combined["profit_level_pct"]
        / combined[
            "median_downside_pct"
        ].abs()
    )

    combined[
        "target_to_p90_downside_ratio"
    ] = (
        combined["profit_level_pct"]
        / combined[
            "p90_severe_downside_pct"
        ].abs()
    )

    # ---------------------------------------------------------
    # Sort strongest probabilities first
    # ---------------------------------------------------------

    combined = combined.sort_values(
        [
            "profit_level_pct",
            "reach_probability_pct",
            "valid_event_count_profit",
        ],
        ascending=[
            True,
            False,
            False,
        ],
    ).reset_index(drop=True)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    combined.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\nSaved:")
    print(OUTPUT_FILE)

    print(
        f"\nRows: {len(combined):,}"
    )

    # ---------------------------------------------------------
    # Focus on original V1 +2.5% target
    # ---------------------------------------------------------

    target_2_5 = combined[
        combined["profit_level_pct"] == 2.5
    ].copy()

    display_columns = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
        "valid_event_count_profit",
        "reach_probability_pct",
        "median_time_minutes",
        "median_downside_pct",
        "p90_severe_downside_pct",
        "p95_severe_downside_pct",
        "worst_downside_pct",
        "target_to_median_downside_ratio",
        "target_to_p90_downside_ratio",
    ]

    print("\n" + "=" * 100)
    print("TOP +2.5% SETUPS: UPSIDE VS DOWNSIDE")
    print("=" * 100)

    print(
        target_2_5[
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()