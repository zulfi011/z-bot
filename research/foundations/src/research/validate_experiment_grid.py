from pathlib import Path

import numpy as np
import pandas as pd

from src.utils.experiment_config import (
    load_experiment_config,
)


RESULTS_DIR = Path("results/tables")
REPORT_DIR = Path("results/reports")

GRID_FILE = (
    RESULTS_DIR
    / "experiment_grid.csv"
)

MASTER_FILE = (
    RESULTS_DIR
    / "average_comparison_master.csv"
)


def main():

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    config = load_experiment_config()

    grid = pd.read_csv(
        GRID_FILE
    )

    master = pd.read_csv(
        MASTER_FILE
    )

    checks = {}

    # ---------------------------------------------------------
    # Expected values from config
    # ---------------------------------------------------------

    expected_assets = set(
        config[
            "data"
        ][
            "assets"
        ]
    )

    expected_timeframes = set(
        config[
            "research"
        ][
            "timeframes"
        ]
    )

    expected_averages = set(
        config[
            "research"
        ][
            "averages"
        ]
    )

    expected_zones = set(
        float(x)
        for x
        in config[
            "research"
        ][
            "touch_zones_pct"
        ]
    )

    # ---------------------------------------------------------
    # Basic row count
    # ---------------------------------------------------------

    expected_total = (
        len(expected_assets)
        * len(expected_timeframes)
        * len(expected_averages)
        * len(expected_zones)
    )

    checks[
        "grid_total_row_count_correct"
    ] = (
        len(grid)
        == expected_total
        == 81
    )

    # ---------------------------------------------------------
    # Allowed values
    # ---------------------------------------------------------

    checks[
        "assets_match_config"
    ] = (
        set(
            grid[
                "asset"
            ]
        )
        == expected_assets
    )

    checks[
        "timeframes_match_config"
    ] = (
        set(
            grid[
                "timeframe"
            ]
        )
        == expected_timeframes
    )

    checks[
        "averages_match_config"
    ] = (
        set(
            grid[
                "average_type"
            ]
            .astype(str)
        )
        == expected_averages
    )

    checks[
        "zones_match_config"
    ] = (
        set(
            grid[
                "touch_zone"
            ]
            .astype(float)
        )
        == expected_zones
    )

    # ---------------------------------------------------------
    # No duplicate setups
    # ---------------------------------------------------------

    setup_columns = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    checks[
        "no_duplicate_configurations"
    ] = (
        ~grid[
            setup_columns
        ]
        .duplicated()
        .any()
    )

    # ---------------------------------------------------------
    # Experiment IDs unique
    # ---------------------------------------------------------

    checks[
        "experiment_ids_unique"
    ] = (
        grid[
            "experiment_id"
        ]
        .is_unique
    )

    checks[
        "experiment_ids_not_missing"
    ] = (
        grid[
            "experiment_id"
        ]
        .notna()
        .all()
    )

    # ---------------------------------------------------------
    # 27 configurations per asset
    # ---------------------------------------------------------

    asset_counts = (
        grid
        .groupby(
            "asset"
        )
        .size()
    )

    checks[
        "27_configurations_per_asset"
    ] = (
        asset_counts
        .eq(27)
        .all()
    )

    # ---------------------------------------------------------
    # 9 configurations per timeframe per asset
    # ---------------------------------------------------------

    timeframe_counts = (
        grid
        .groupby(
            [
                "asset",
                "timeframe",
            ]
        )
        .size()
    )

    checks[
        "9_per_asset_timeframe"
    ] = (
        timeframe_counts
        .eq(9)
        .all()
    )

    # ---------------------------------------------------------
    # 9 configurations per average per asset
    # ---------------------------------------------------------

    average_counts = (
        grid
        .groupby(
            [
                "asset",
                "average_type",
            ]
        )
        .size()
    )

    checks[
        "9_per_asset_average"
    ] = (
        average_counts
        .eq(9)
        .all()
    )

    # ---------------------------------------------------------
    # 9 configurations per zone per asset
    # ---------------------------------------------------------

    zone_counts = (
        grid
        .groupby(
            [
                "asset",
                "touch_zone",
            ]
        )
        .size()
    )

    checks[
        "9_per_asset_zone"
    ] = (
        zone_counts
        .eq(9)
        .all()
    )

    # ---------------------------------------------------------
    # Compare against historical research master
    # ---------------------------------------------------------

    master_setups = (
        master[
            setup_columns
        ]
        .copy()
    )

    master_setups[
        "average_type"
    ] = (
        master_setups[
            "average_type"
        ]
        .astype(str)
    )

    master_setups[
        "touch_zone"
    ] = (
        master_setups[
            "touch_zone"
        ]
        .astype(float)
    )

    grid_setups = (
        grid[
            setup_columns
        ]
        .copy()
    )

    grid_setups[
        "average_type"
    ] = (
        grid_setups[
            "average_type"
        ]
        .astype(str)
    )

    grid_setups[
        "touch_zone"
    ] = (
        grid_setups[
            "touch_zone"
        ]
        .astype(float)
    )

    grid_sorted = (
        grid_setups
        .sort_values(
            setup_columns
        )
        .reset_index(
            drop=True
        )
    )

    master_sorted = (
        master_setups
        .sort_values(
            setup_columns
        )
        .reset_index(
            drop=True
        )
    )

    checks[
        "historical_master_has_81_rows"
    ] = (
        len(
            master_sorted
        )
        == 81
    )

    checks[
        "config_grid_matches_historical_research"
    ] = (
        grid_sorted.equals(
            master_sorted
        )
    )

    # ---------------------------------------------------------
    # Verify deterministic experiment IDs
    # ---------------------------------------------------------

    expected_ids = (
        grid.apply(
            lambda row:
            f"{row['asset']}_"
            f"{row['timeframe']}_"
            f"{row['average_type']}_"
            f"zone_"
            f"{str(float(row['touch_zone'])).replace('.', '_')}",
            axis=1,
        )
    )

    checks[
        "experiment_ids_deterministic"
    ] = (
        grid[
            "experiment_id"
        ]
        .astype(str)
        .equals(
            expected_ids
            .astype(str)
        )
    )

    # ---------------------------------------------------------
    # Save report
    # ---------------------------------------------------------

    report = pd.DataFrame(
        [
            {
                "check": name,
                "pass": bool(
                    passed
                ),
            }
            for name, passed
            in checks.items()
        ]
    )

    output_file = (
        REPORT_DIR
        / "experiment_grid_validation.csv"
    )

    report.to_csv(
        output_file,
        index=False,
    )

    failed = report[
        report[
            "pass"
        ]
        == False
    ]

    print(
        "\n"
        + "=" * 90
    )

    print(
        "EXPERIMENT GRID VALIDATION"
    )

    print(
        "=" * 90
    )

    if len(
        failed
    ) == 0:

        print(
            "ALL CHECKS PASS"
        )

    else:

        print(
            "FAILED CHECKS:"
        )

        print(
            failed.to_string(
                index=False
            )
        )

    print(
        "\nChecks:",
        len(
            report
        ),
    )

    print(
        "Passed:",
        int(
            report[
                "pass"
            ].sum()
        ),
    )

    print(
        "Failed:",
        int(
            (
                ~report[
                    "pass"
                ]
            ).sum()
        ),
    )

    print(
        "\nReport saved:"
    )

    print(
        output_file
    )


if __name__ == "__main__":
    main()