from pathlib import Path

import pandas as pd


TABLES_DIR = Path("results/tables")

SUMMARY_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary.csv"
)

FORWARD_FILE = (
    TABLES_DIR
    / "forward_return_statistics.csv"
)

OUTPUT_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary.csv"
)

BACKUP_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary_pre_forward_returns.csv"
)


KEYS = [
    "asset",
    "timeframe",
    "average_type",
    "touch_zone",
]


HORIZONS = [
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "24h",
]


def main():

    summary = pd.read_csv(
        SUMMARY_FILE
    )

    forward = pd.read_csv(
        FORWARD_FILE
    )

    # ---------------------------------------------------------
    # Basic validation
    # ---------------------------------------------------------

    if len(summary) != 81:
        raise ValueError(
            f"Expected 81 summary rows, found {len(summary)}"
        )

    if len(forward) != 81:
        raise ValueError(
            f"Expected 81 forward-return rows, found {len(forward)}"
        )

    if summary[KEYS].duplicated().any():
        raise ValueError(
            "Duplicate configurations found in Stage 1 summary."
        )

    if forward[KEYS].duplicated().any():
        raise ValueError(
            "Duplicate configurations found in forward-return table."
        )

    # ---------------------------------------------------------
    # Normalize merge-key types
    # ---------------------------------------------------------

    summary["average_type"] = (
        summary["average_type"]
        .astype(str)
    )

    forward["average_type"] = (
        forward["average_type"]
        .astype(str)
    )

    summary["touch_zone"] = (
        summary["touch_zone"]
        .astype(float)
    )

    forward["touch_zone"] = (
        forward["touch_zone"]
        .astype(float)
    )

    # ---------------------------------------------------------
    # Protect against running this script twice
    # ---------------------------------------------------------

    forward_columns = []

    for horizon in HORIZONS:

        forward_columns += [
            f"return_{horizon}_valid_count",
            f"return_{horizon}_median_pct",
            f"return_{horizon}_mean_pct",
        ]

    columns_to_remove = [
        "forward_return_total_event_count",
        *forward_columns,
    ]

    existing_forward_columns = [
        column
        for column in columns_to_remove
        if column in summary.columns
    ]

    if existing_forward_columns:

        print(
            "Existing forward-return columns found "
            "in Stage 1 summary."
        )

        print(
            "They will be replaced from the latest "
            "forward_return_statistics.csv."
        )

        summary = summary.drop(
            columns=existing_forward_columns
        )

    # ---------------------------------------------------------
    # Rename total touch-event count
    #
    # This is NOT the same as Stage 1 event_count.
    #
    # forward table event_count:
    #     all touch events
    #
    # Stage 1 event_count:
    #     events with a complete 24h observation
    # ---------------------------------------------------------

    forward = forward.rename(
        columns={
            "event_count":
            "forward_return_total_event_count"
        }
    )

    # ---------------------------------------------------------
    # Merge
    # ---------------------------------------------------------

    merged = summary.merge(
        forward,
        on=KEYS,
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    # ---------------------------------------------------------
    # Every setup must exist in both tables
    # ---------------------------------------------------------

    if not (
        merged["_merge"]
        == "both"
    ).all():

        bad = merged[
            merged["_merge"]
            != "both"
        ][
            KEYS
            + [
                "_merge",
            ]
        ]

        raise ValueError(
            "Configuration mismatch between "
            "Stage 1 summary and forward-return table:\n"
            + bad.to_string(
                index=False
            )
        )

    merged = merged.drop(
        columns="_merge"
    )

    # ---------------------------------------------------------
    # Event-count consistency
    #
    # We already proved:
    #
    # Stage1 event_count
    #     ==
    # return_24h_valid_count
    #
    # for all 81 configurations.
    # ---------------------------------------------------------

    if not (
        merged[
            "event_count"
        ]
        ==
        merged[
            "return_24h_valid_count"
        ]
    ).all():

        bad = merged[
            merged[
                "event_count"
            ]
            !=
            merged[
                "return_24h_valid_count"
            ]
        ][
            KEYS
            + [
                "event_count",
                "return_24h_valid_count",
            ]
        ]

        raise ValueError(
            "Stage 1 event count does not match "
            "24h valid forward-return count:\n"
            + bad.to_string(
                index=False
            )
        )

    # ---------------------------------------------------------
    # Total forward-return events must be >= 24h valid events
    # ---------------------------------------------------------

    if not (
        merged[
            "forward_return_total_event_count"
        ]
        >=
        merged[
            "return_24h_valid_count"
        ]
    ).all():

        bad = merged[
            merged[
                "forward_return_total_event_count"
            ]
            <
            merged[
                "return_24h_valid_count"
            ]
        ][
            KEYS
            + [
                "forward_return_total_event_count",
                "return_24h_valid_count",
            ]
        ]

        raise ValueError(
            "Forward total event count is smaller "
            "than the 24h valid event count:\n"
            + bad.to_string(
                index=False
            )
        )

    # ---------------------------------------------------------
    # Validate forward-return columns
    # ---------------------------------------------------------

    missing_columns = [
        column
        for column in forward_columns
        if column not in merged.columns
    ]

    if missing_columns:

        raise ValueError(
            "Missing forward-return columns:\n"
            + str(
                missing_columns
            )
        )

    missing_values = (
        merged[
            forward_columns
        ]
        .isna()
        .sum()
        .sum()
    )

    if missing_values != 0:

        raise ValueError(
            "Missing values found in "
            f"forward-return metrics: {missing_values}"
        )

    # ---------------------------------------------------------
    # Horizon count logic
    #
    # Longer horizons cannot have more valid observations
    # than shorter horizons.
    # ---------------------------------------------------------

    valid_count_columns = [
        f"return_{horizon}_valid_count"
        for horizon in HORIZONS
    ]

    for previous, current in zip(
        valid_count_columns,
        valid_count_columns[1:],
    ):

        if not (
            merged[
                previous
            ]
            >=
            merged[
                current
            ]
        ).all():

            bad = merged[
                merged[
                    previous
                ]
                <
                merged[
                    current
                ]
            ][
                KEYS
                + [
                    previous,
                    current,
                ]
            ]

            raise ValueError(
                "Forward-return valid counts "
                "increase at a longer horizon:\n"
                + bad.to_string(
                    index=False
                )
            )

    # ---------------------------------------------------------
    # Final row validation
    # ---------------------------------------------------------

    if len(merged) != 81:

        raise ValueError(
            f"Expected 81 final rows, found {len(merged)}"
        )

    if merged[KEYS].duplicated().any():

        raise ValueError(
            "Duplicate configurations found after merge."
        )

    # ---------------------------------------------------------
    # Backup original Stage 1 summary
    #
    # Only create once so we preserve the original
    # pre-forward-return version.
    # ---------------------------------------------------------

    if not BACKUP_FILE.exists():

        original_summary = pd.read_csv(
            SUMMARY_FILE
        )

        original_summary.to_csv(
            BACKUP_FILE,
            index=False,
        )

        print(
            f"Backup saved: {BACKUP_FILE}"
        )

    else:

        print(
            f"Backup already exists: {BACKUP_FILE}"
        )

    # ---------------------------------------------------------
    # Sort and save corrected Stage 1 summary
    # ---------------------------------------------------------

    merged = merged.sort_values(
        KEYS
    ).reset_index(
        drop=True
    )

    merged.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # ---------------------------------------------------------
    # Report
    # ---------------------------------------------------------

    print(
        "\n"
        + "=" * 90
    )

    print(
        "STAGE 1 SUMMARY + FORWARD RETURNS"
    )

    print(
        "=" * 90
    )

    print(
        "\nRows:",
        len(
            merged
        ),
    )

    print(
        "Columns:",
        len(
            merged.columns
        ),
    )

    print(
        "\nForward-return metric columns added:",
        len(
            forward_columns
        ),
    )

    print(
        "\nMissing forward-return values:",
        int(
            merged[
                forward_columns
            ]
            .isna()
            .sum()
            .sum()
        ),
    )

    print(
        "\nEvent-count validation:"
    )

    print(
        "Stage1 event_count == "
        "return_24h_valid_count:",
        int(
            (
                merged[
                    "event_count"
                ]
                ==
                merged[
                    "return_24h_valid_count"
                ]
            ).sum()
        ),
        "/",
        len(
            merged
        ),
    )

    print(
        "Forward total >= "
        "return_24h_valid_count:",
        int(
            (
                merged[
                    "forward_return_total_event_count"
                ]
                >=
                merged[
                    "return_24h_valid_count"
                ]
            ).sum()
        ),
        "/",
        len(
            merged
        ),
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()