from pathlib import Path

import pandas as pd


ASSETS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

TIMEFRAMES = [
    "1m",
    "3m",
    "5m",
]

HORIZONS = [
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "24h",
]

RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")

OUTPUT_FILE = (
    RESULTS_DIR
    / "forward_return_statistics.csv"
)


def main():

    rows = []

    for asset in ASSETS:

        for timeframe in TIMEFRAMES:

            input_file = (
                RESEARCH_DIR
                / asset
                / f"{asset}_{timeframe}_touch_events_with_trailing_research.parquet"
            )

            if not input_file.exists():
                raise FileNotFoundError(
                    f"Missing input file: {input_file}"
                )

            print(
                f"Processing {asset} {timeframe}"
            )

            columns = [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
            ]

            columns += [
                f"return_{horizon}_pct"
                for horizon in HORIZONS
            ]

            df = pd.read_parquet(
                input_file,
                columns=columns,
            )

            grouped = df.groupby(
                [
                    "asset",
                    "timeframe",
                    "average_type",
                    "touch_zone",
                ],
                dropna=False,
                observed=True,
            )

            for (
                asset_value,
                timeframe_value,
                average_type,
                touch_zone,
            ), group in grouped:

                row = {
                    "asset": asset_value,
                    "timeframe": timeframe_value,
                    "average_type": average_type,
                    "touch_zone": float(
                        touch_zone
                    ),
                    "event_count": len(
                        group
                    ),
                }

                for horizon in HORIZONS:

                    column = (
                        f"return_{horizon}_pct"
                    )

                    values = (
                        pd.to_numeric(
                            group[column],
                            errors="coerce",
                        )
                        .dropna()
                    )

                    row[
                        f"return_{horizon}_valid_count"
                    ] = len(values)

                    if len(values) == 0:

                        row[
                            f"return_{horizon}_median_pct"
                        ] = float("nan")

                        row[
                            f"return_{horizon}_mean_pct"
                        ] = float("nan")

                    else:

                        row[
                            f"return_{horizon}_median_pct"
                        ] = values.median()

                        row[
                            f"return_{horizon}_mean_pct"
                        ] = values.mean()

                rows.append(
                    row
                )

    result = pd.DataFrame(
        rows
    )

    result = result.sort_values(
        [
            "asset",
            "timeframe",
            "average_type",
            "touch_zone",
        ]
    ).reset_index(
        drop=True
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        "\n"
        + "=" * 90
    )

    print(
        "FORWARD RETURN STATISTICS"
    )

    print(
        "=" * 90
    )

    print(
        "\nRows:",
        len(result),
    )

    print(
        "\nRows per asset:"
    )

    print(
        result.groupby(
            "asset"
        )
        .size()
        .to_string()
    )

    print(
        "\nMissing values:"
    )

    print(
        result.isna()
        .sum()
        .to_string()
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()