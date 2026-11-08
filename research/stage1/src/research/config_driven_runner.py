from pathlib import Path

import numpy as np
import pandas as pd
import argparse

from src.utils.experiment_config import (
    load_experiment_config,
)

from src.research.experiment_grid import (
    build_experiment_grid,
)


RESULTS_DIR = Path("results/tables")

MASTER_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)


def main():

    # ---------------------------------------------------------
    # Load experiment definition
    # ---------------------------------------------------------

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default="config/experiments/v1_stage1.yaml",
    )

    args = parser.parse_args()

    config = load_experiment_config(
        args.config
    )

    grid = (
        build_experiment_grid(
            config
        )
    )

    master = pd.read_csv(
        MASTER_FILE
    )

    print(
        "\n"
        + "=" * 100
    )

    print(
        "CONFIG-DRIVEN RESEARCH RUNNER"
    )

    print(
        "=" * 100
    )

    print(
        "\nExperiment:"
    )

    print(
        config[
            "experiment"
        ][
            "name"
        ]
    )

    print(
        "\nConfigurations loaded:",
        len(
            grid
        ),
    )

    results = []

    # ---------------------------------------------------------
    # Run each configuration
    #
    # For Part 21 we are not recalculating the historical
    # research. We are proving that the config can drive the
    # selection of each researched setup.
    # ---------------------------------------------------------

    for _, experiment in grid.iterrows():

        asset = (
            experiment[
                "asset"
            ]
        )

        timeframe = (
            experiment[
                "timeframe"
            ]
        )

        average_type = (
            experiment[
                "average_type"
            ]
        )

        touch_zone = float(
            experiment[
                "touch_zone"
            ]
        )

        matched = master[
            (
                master[
                    "asset"
                ]
                == asset
            )
            &
            (
                master[
                    "timeframe"
                ]
                == timeframe
            )
            &
            (
                master[
                    "average_type"
                ]
                .astype(str)
                == str(
                    average_type
                )
            )
            &
            (
                np.isclose(
                    master[
                        "touch_zone"
                    ]
                    .astype(float),
                    touch_zone,
                )
            )
        ]

        if len(
            matched
        ) != 1:

            raise ValueError(
                "Expected exactly one research row for "
                f"{experiment['experiment_id']}, "
                f"found {len(matched)}"
            )

        row = matched.iloc[
            0
        ]

        results.append(
            {
                "experiment_id": (
                    experiment[
                        "experiment_id"
                    ]
                ),
                "asset": asset,
                "timeframe": timeframe,
                "average_type": (
                    average_type
                ),
                "touch_zone": (
                    touch_zone
                ),
                "event_count": (
                    row[
                        "event_count"
                    ]
                ),
                "reach_probability_pct": (
                    row[
                        "reach_probability_pct"
                    ]
                ),
                "mae_24h_median_pct": (
                    row[
                        "mae_24h_median_pct"
                    ]
                ),
                "mfe_24h_median_pct": (
                    row[
                        "mfe_24h_median_pct"
                    ]
                ),
                "median_mfe_mae_ratio": (
                    row[
                        "median_mfe_mae_ratio"
                    ]
                ),
            }
        )

    results_df = pd.DataFrame(
        results
    )

    output_file = (
        RESULTS_DIR
        / "config_driven_research_results.csv"
    )

    results_df.to_csv(
        output_file,
        index=False,
    )

    print(
        "\nProcessed configurations:",
        len(
            results_df
        ),
    )

    print(
        "\nConfigurations per asset:"
    )

    print(
        results_df
        .groupby(
            "asset"
        )
        .size()
        .to_string()
    )

    print(
        "\nExample first 10:"
    )

    print(
        results_df
        .head(
            10
        )
        .to_string(
            index=False
        )
    )

    print(
        "\nSaved:"
    )

    print(
        output_file
    )


if __name__ == "__main__":
    main()