from pathlib import Path

import pandas as pd


INPUT_FILE = Path(
    "results/tables/profit_reach_statistics.csv"
)

OUTPUT_DIR = Path(
    "results/tables"
)


def main():

    df = pd.read_csv(INPUT_FILE)

    # ---------------------------------------------------------
    # Minimum sample-size protection
    # ---------------------------------------------------------

    MIN_VALID_EVENTS = 1000

    filtered = df[
        df["valid_event_count"]
        >= MIN_VALID_EVENTS
    ].copy()

    # ---------------------------------------------------------
    # Rank separately for every profit target
    # ---------------------------------------------------------

    filtered["probability_rank"] = (
        filtered.groupby(
            "profit_level_pct"
        )["reach_probability_pct"]
        .rank(
            method="dense",
            ascending=False,
        )
    )

    filtered["speed_rank"] = (
        filtered.groupby(
            "profit_level_pct"
        )["median_time_minutes"]
        .rank(
            method="dense",
            ascending=True,
        )
    )

    # ---------------------------------------------------------
    # Simple combined research score
    #
    # Probability is the main factor.
    # Faster target achievement gets a smaller bonus.
    #
    # This is NOT a trading score yet.
    # ---------------------------------------------------------

    filtered["research_score"] = (
        filtered["reach_probability_pct"]
        - (
            filtered["median_time_minutes"]
            / 1440
            * 5
        )
    )

    filtered["overall_rank"] = (
        filtered.groupby(
            "profit_level_pct"
        )["research_score"]
        .rank(
            method="dense",
            ascending=False,
        )
    )

    # ---------------------------------------------------------
    # Sort best setups first
    # ---------------------------------------------------------

    ranked = filtered.sort_values(
        [
            "profit_level_pct",
            "overall_rank",
            "valid_event_count",
        ],
        ascending=[
            True,
            True,
            False,
        ],
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    full_output = (
        OUTPUT_DIR
        / "profit_reach_ranked_setups.csv"
    )

    ranked.to_csv(
        full_output,
        index=False,
    )

    # ---------------------------------------------------------
    # Top 10 setups per target
    # ---------------------------------------------------------

    top10 = (
        ranked[
            ranked["overall_rank"] <= 10
        ]
        .copy()
    )

    top10_output = (
        OUTPUT_DIR
        / "profit_reach_top10_setups.csv"
    )

    top10.to_csv(
        top10_output,
        index=False,
    )

    # ---------------------------------------------------------
    # Display useful summary
    # ---------------------------------------------------------

    print("\nSaved:")
    print(full_output)
    print(top10_output)

    print(
        f"\nRows after minimum "
        f"{MIN_VALID_EVENTS:,}-event filter: "
        f"{len(ranked):,}"
    )

    display_columns = [
        "profit_level_pct",
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
        "valid_event_count",
        "reach_probability_pct",
        "median_time_minutes",
        "research_score",
        "overall_rank",
    ]

    for target in sorted(
        ranked["profit_level_pct"].unique()
    ):

        print("\n" + "=" * 80)
        print(
            f"TOP SETUPS FOR +{target}%"
        )
        print("=" * 80)

        subset = (
            ranked[
                ranked["profit_level_pct"]
                == target
            ]
            .head(10)
        )

        print(
            subset[
                display_columns
            ].to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()