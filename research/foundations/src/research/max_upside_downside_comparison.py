from pathlib import Path

import pandas as pd


UPSIDE_FILE = Path(
    "results/tables/upside_statistics.csv"
)

DOWNSIDE_FILE = Path(
    "results/tables/downside_statistics.csv"
)

OUTPUT_FILE = Path(
    "results/tables/max_upside_downside_comparison.csv"
)


def main():

    upside = pd.read_csv(
        UPSIDE_FILE
    )

    downside = pd.read_csv(
        DOWNSIDE_FILE
    )

    # ---------------------------------------------------------
    # Compare the same 24-hour window on both sides.
    # ---------------------------------------------------------

    upside_24h = upside[
        upside["window"] == "24h"
    ].copy()

    downside_24h = downside[
        downside["window"] == "24h"
    ].copy()

    combined = upside_24h.merge(
        downside_24h[
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "valid_event_count",
                "mean_downside_pct",
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
            "_upside",
            "_downside",
        ),
        validate="one_to_one",
    )

    # ---------------------------------------------------------
    # Descriptive comparison ratios.
    #
    # These are NOT trade profitability metrics.
    # They compare favorable and adverse opportunity only.
    # ---------------------------------------------------------

    combined[
        "median_upside_to_downside_ratio"
    ] = (
        combined[
            "median_upside_pct"
        ]
        / combined[
            "median_downside_pct"
        ].abs()
    )

    combined[
        "p90_upside_to_severe_downside_ratio"
    ] = (
        combined[
            "p90_upside_pct"
        ]
        / combined[
            "p90_severe_downside_pct"
        ].abs()
    )

    # ---------------------------------------------------------
    # A simple descriptive balance:
    #
    # positive = median favorable excursion is larger
    # negative = median adverse excursion is larger
    # ---------------------------------------------------------

    combined[
        "median_excursion_balance_pct"
    ] = (
        combined[
            "median_upside_pct"
        ]
        - combined[
            "median_downside_pct"
        ].abs()
    )

    combined = combined.sort_values(
        [
            "median_upside_to_downside_ratio",
            "median_upside_pct",
        ],
        ascending=[
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

    display_columns = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",

        "valid_event_count_upside",

        "median_upside_pct",
        "median_downside_pct",

        "p90_upside_pct",
        "p90_severe_downside_pct",

        "p95_upside_pct",
        "p95_severe_downside_pct",

        "best_upside_pct",
        "worst_downside_pct",

        "median_upside_to_downside_ratio",
        "median_excursion_balance_pct",
    ]

    print("\n" + "=" * 110)
    print("TOP 24H MAXIMUM UPSIDE VS MAXIMUM DOWNSIDE SETUPS")
    print("=" * 110)

    print(
        combined[
            display_columns
        ]
        .head(30)
        .to_string(
            index=False
        )
    )

    # ---------------------------------------------------------
    # Show our main candidate separately.
    # ---------------------------------------------------------

    sol_candidate = combined[
        (combined["asset"] == "SOLUSDT")
        & (combined["average_type"] == "15d")
        & (combined["touch_zone"] == 0.5)
    ]

    print("\n" + "=" * 110)
    print("SOLUSDT | 15D | 0.5% TOUCH ZONE")
    print("=" * 110)

    print(
        sol_candidate[
            display_columns
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()