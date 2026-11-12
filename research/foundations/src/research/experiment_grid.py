from itertools import product
from pathlib import Path

import pandas as pd

from src.utils.experiment_config import (
    load_experiment_config,
)


RESULTS_DIR = Path(
    "results/tables"
)


def build_experiment_grid(
    config: dict,
) -> pd.DataFrame:

    assets = (
        config[
            "data"
        ][
            "assets"
        ]
    )

    timeframes = (
        config[
            "research"
        ][
            "timeframes"
        ]
    )

    averages = (
        config[
            "research"
        ][
            "averages"
        ]
    )

    touch_zones = (
        config[
            "research"
        ][
            "touch_zones_pct"
        ]
    )

    rows = []

    for (
        asset,
        timeframe,
        average,
        touch_zone,
    ) in product(
        assets,
        timeframes,
        averages,
        touch_zones,
    ):

        experiment_id = (
            f"{asset}_"
            f"{timeframe}_"
            f"{average}_"
            f"zone_{str(touch_zone).replace('.', '_')}"
        )

        rows.append(
            {
                "experiment_id": experiment_id,
                "asset": asset,
                "timeframe": timeframe,
                "average_type": average,
                "touch_zone": float(
                    touch_zone
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def main():

    config = (
        load_experiment_config()
    )

    grid = (
        build_experiment_grid(
            config
        )
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        RESULTS_DIR
        / "experiment_grid.csv"
    )

    grid.to_csv(
        output_file,
        index=False,
    )

    print(
        "\n"
        + "=" * 90
    )

    print(
        "EXPERIMENT GRID"
    )

    print(
        "=" * 90
    )

    print(
        grid.to_string(
            index=False
        )
    )

    print(
        "\nTotal configurations:",
        len(
            grid
        ),
    )

    print(
        "\nConfigurations per asset:"
    )

    print(
        grid.groupby(
            "asset"
        )
        .size()
        .to_string()
    )

    print(
        "\nSaved:"
    )

    print(
        output_file
    )


if __name__ == "__main__":
    main()