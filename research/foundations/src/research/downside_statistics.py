from pathlib import Path

import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")


WINDOWS = ["1h", "4h", "24h"]


def calculate_statistics(
    symbol: str,
    timeframe: str,
) -> list[dict]:

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_max_downside.parquet"
        )
    )

    df = pd.read_parquet(input_file)

    rows = []

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

        for window in WINDOWS:

            complete_column = (
                f"downside_window_complete_{window}"
            )

            downside_column = (
                f"max_downside_{window}_pct"
            )

            complete = (
                group[
                    complete_column
                ]
                .astype(bool)
            )

            valid = (
                group.loc[
                    complete,
                    downside_column,
                ]
                .dropna()
                .astype(float)
            )

            valid_count = len(valid)

            incomplete_count = (
                len(group)
                - valid_count
            )

            if valid_count > 0:

                mean_downside = (
                    valid.mean()
                )

                median_downside = (
                    valid.median()
                )

                p25_downside = (
                    valid.quantile(0.25)
                )

                p75_downside = (
                    valid.quantile(0.75)
                )

                p90_downside = (
                    valid.quantile(0.10)
                )

                p95_downside = (
                    valid.quantile(0.05)
                )

                worst_downside = (
                    valid.min()
                )

                best_downside = (
                    valid.max()
                )

            else:

                mean_downside = None
                median_downside = None
                p25_downside = None
                p75_downside = None
                p90_downside = None
                p95_downside = None
                worst_downside = None
                best_downside = None

            rows.append(
                {
                    "asset": symbol,
                    "timeframe": timeframe,
                    "average_type": average_type,
                    "touch_zone": touch_zone,
                    "window": window,

                    "total_event_rows": len(group),
                    "valid_event_count": valid_count,
                    "incomplete_count": incomplete_count,

                    "mean_downside_pct": (
                        mean_downside
                    ),

                    "median_downside_pct": (
                        median_downside
                    ),

                    "p25_downside_pct": (
                        p25_downside
                    ),

                    "p75_downside_pct": (
                        p75_downside
                    ),

                    "p90_severe_downside_pct": (
                        p90_downside
                    ),

                    "p95_severe_downside_pct": (
                        p95_downside
                    ),

                    "worst_downside_pct": (
                        worst_downside
                    ),

                    "best_downside_pct": (
                        best_downside
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

    window_order = {
        "1h": 1,
        "4h": 2,
        "24h": 3,
    }

    results["_window_order"] = (
        results["window"]
        .map(window_order)
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
        .reset_index(drop=True)
    )

    output_file = (
        RESULTS_DIR
        / "downside_statistics.csv"
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
                "window",
                "valid_event_count",
                "median_downside_pct",
                "p90_severe_downside_pct",
                "worst_downside_pct",
            ]
        ]
        .head(30)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()