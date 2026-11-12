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
            f"_touch_events_with_max_upside.parquet"
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
                f"upside_window_complete_{window}"
            )

            upside_column = (
                f"max_upside_{window}_pct"
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
                    upside_column,
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

                mean_upside = (
                    valid.mean()
                )

                median_upside = (
                    valid.median()
                )

                p25_upside = (
                    valid.quantile(0.25)
                )

                p75_upside = (
                    valid.quantile(0.75)
                )

                p90_upside = (
                    valid.quantile(0.90)
                )

                p95_upside = (
                    valid.quantile(0.95)
                )

                best_upside = (
                    valid.max()
                )

                worst_upside = (
                    valid.min()
                )

            else:

                mean_upside = None
                median_upside = None
                p25_upside = None
                p75_upside = None
                p90_upside = None
                p95_upside = None
                best_upside = None
                worst_upside = None

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

                    "mean_upside_pct": (
                        mean_upside
                    ),

                    "median_upside_pct": (
                        median_upside
                    ),

                    "p25_upside_pct": (
                        p25_upside
                    ),

                    "p75_upside_pct": (
                        p75_upside
                    ),

                    "p90_upside_pct": (
                        p90_upside
                    ),

                    "p95_upside_pct": (
                        p95_upside
                    ),

                    "best_upside_pct": (
                        best_upside
                    ),

                    "worst_upside_pct": (
                        worst_upside
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
        / "upside_statistics.csv"
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
                "median_upside_pct",
                "p90_upside_pct",
                "best_upside_pct",
            ]
        ]
        .head(30)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()