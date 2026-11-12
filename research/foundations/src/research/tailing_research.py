from pathlib import Path

import numpy as np
import pandas as pd


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "3m", "5m"]

RAW_DIR = Path("data/raw")
RESEARCH_DIR = Path("data/research")
RESULTS_DIR = Path("results/tables")

# Fraction of accumulated profit that may be given back
# from the running peak.
#
# Example:
# touch price = 100
# peak = 105
# 30% giveback => trail = 103.50
TRAIL_GIVEBACKS = {
    "10": 0.10,
    "20": 0.20,
    "30": 0.30,
    "40": 0.40,
    "50": 0.50,
}

OBSERVATION_MINUTES = 24 * 60

# Keeps memory reasonable while still vectorizing the 24h paths.
CHUNK_SIZE = 2000


def load_raw(symbol: str) -> pd.DataFrame:

    input_file = (
        RAW_DIR
        / symbol
        / f"{symbol}_1m.parquet"
    )

    df = pd.read_parquet(
        input_file,
        columns=[
            "open_time",
            "high",
            "low",
        ],
    )

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        utc=True,
    )

    df = (
        df
        .sort_values("open_time")
        .drop_duplicates(
            subset=["open_time"]
        )
        .reset_index(drop=True)
    )

    return df


def load_events(
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:

    input_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_post_activation.parquet"
        )
    )

    df = pd.read_parquet(
        input_file
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        utc=True,
    )

    df[
        "trailing_activation_timestamp"
    ] = pd.to_datetime(
        df[
            "trailing_activation_timestamp"
        ],
        utc=True,
    )

    df[
        "post_activation_start_timestamp"
    ] = pd.to_datetime(
        df[
            "post_activation_start_timestamp"
        ],
        utc=True,
    )

    return df


def simulate_trailing_for_unique_events(
    unique_events: pd.DataFrame,
    raw: pd.DataFrame,
) -> pd.DataFrame:

    raw_times = pd.DatetimeIndex(
        raw["open_time"]
    )

    highs = raw[
        "high"
    ].to_numpy(
        dtype=np.float64
    )

    lows = raw[
        "low"
    ].to_numpy(
        dtype=np.float64
    )

    n = len(
        unique_events
    )

    activated = (
        unique_events[
            "trailing_activation_reached"
        ]
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )

    start_indices = np.full(
        n,
        -1,
        dtype=np.int64,
    )

    activated_positions = np.flatnonzero(
        activated
    )

    if len(
        activated_positions
    ) > 0:

        start_indices[
            activated_positions
        ] = raw_times.get_indexer(
            unique_events.loc[
                activated,
                "post_activation_start_timestamp",
            ]
        )

    requested_end = (
        start_indices
        + OBSERVATION_MINUTES
        - 1
    )

    full_window = (
        activated
        & (start_indices >= 0)
        & (
            requested_end
            < len(raw)
        )
    )

    unique_events[
        "trailing_research_window_complete_24h"
    ] = pd.array(
        [
            pd.NA
        ] * n,
        dtype="boolean",
    )

    unique_events.loc[
        activated,
        "trailing_research_window_complete_24h",
    ] = False

    unique_events.loc[
        full_window,
        "trailing_research_window_complete_24h",
    ] = True

    # Initialize output columns.
    for (
        trail_name,
        giveback,
    ) in TRAIL_GIVEBACKS.items():

        unique_events[
            f"trail_{trail_name}_giveback_pct"
        ] = (
            giveback
            * 100
        )

        unique_events[
            f"trail_{trail_name}_outcome"
        ] = pd.Series(
            pd.NA,
            index=unique_events.index,
            dtype="string",
        )

        unique_events[
            f"trail_{trail_name}_event_timestamp"
        ] = pd.Series(
            pd.NaT,
            index=unique_events.index,
            dtype="datetime64[us, UTC]",
        )

        unique_events[
            f"trail_{trail_name}_time_minutes"
        ] = np.nan

        unique_events[
            f"trail_{trail_name}_peak_before_event_price"
        ] = np.nan

        unique_events[
            f"trail_{trail_name}_old_trail_price"
        ] = np.nan

        unique_events[
            f"trail_{trail_name}_old_locked_profit_pct"
        ] = np.nan

        unique_events[
            f"trail_{trail_name}_new_peak_same_candle_price"
        ] = np.nan

        unique_events[
            f"trail_{trail_name}_tightened_trail_same_candle_price"
        ] = np.nan

        unique_events[
            f"trail_{trail_name}_tightened_locked_profit_same_candle_pct"
        ] = np.nan

    # Non-activated events are intentionally left NA.
    valid_positions = np.flatnonzero(
        activated
        & (start_indices >= 0)
    )

    touch_prices_all = (
        unique_events[
            "price"
        ]
        .to_numpy(
            dtype=np.float64
        )
    )

    activation_prices_all = (
        unique_events[
            "trailing_activation_price"
        ]
        .to_numpy(
            dtype=np.float64
        )
    )

    print(
        f"  Activated with valid post-start: "
        f"{len(valid_positions):,}"
    )

    # ---------------------------------------------------------
    # Vectorized chunk simulation.
    #
    # At the START of each 1m candle, the active trail is based
    # only on the running peak from PRIOR candles.
    #
    # If current low <= old trail:
    #     resolved trigger (no intrabar ambiguity)
    #
    # Else, if current high makes a new peak and current low is
    # below the newly tightened trail:
    #     ambiguous_same_candle
    #
    # We stop at the first resolved/ambiguous trail event.
    # ---------------------------------------------------------

    for chunk_start in range(
        0,
        len(valid_positions),
        CHUNK_SIZE,
    ):

        chunk_positions = valid_positions[
            chunk_start:
            chunk_start + CHUNK_SIZE
        ]

        chunk_n = len(
            chunk_positions
        )

        chunk_start_indices = (
            start_indices[
                chunk_positions
            ]
        )

        touch_prices = (
            touch_prices_all[
                chunk_positions
            ]
        )

        activation_prices = (
            activation_prices_all[
                chunk_positions
            ]
        )

        # Some end-of-dataset events do not have 1440 future
        # candles. Pad missing future positions with the final
        # raw index, then mask them out using available_lengths.
        available_lengths = np.minimum(
            OBSERVATION_MINUTES,
            len(raw)
            - chunk_start_indices,
        )

        offsets = np.arange(
            OBSERVATION_MINUTES,
            dtype=np.int64,
        )

        index_matrix = (
            chunk_start_indices[
                :,
                None
            ]
            + offsets[
                None,
                :
            ]
        )

        valid_matrix = (
            offsets[
                None,
                :
            ]
            < available_lengths[
                :,
                None
            ]
        )

        safe_index_matrix = np.minimum(
            index_matrix,
            len(raw) - 1,
        )

        high_matrix = highs[
            safe_index_matrix
        ].copy()

        low_matrix = lows[
            safe_index_matrix
        ].copy()

        # Missing/padded candles must never create a hit.
        high_matrix[
            ~valid_matrix
        ] = -np.inf

        low_matrix[
            ~valid_matrix
        ] = np.inf

        # running_peak_after_current includes current candle high
        running_peak_after = np.maximum.accumulate(
            np.maximum(
                high_matrix,
                activation_prices[
                    :,
                    None
                ],
            ),
            axis=1,
        )

        # Peak known at the START of current candle:
        # activation threshold for first post-activation candle,
        # then running peak through prior candle.
        prior_peak = np.empty_like(
            running_peak_after
        )

        prior_peak[
            :,
            0
        ] = activation_prices

        prior_peak[
            :,
            1:
        ] = running_peak_after[
            :,
            :-1
        ]

        new_peak = np.maximum(
            prior_peak,
            high_matrix,
        )

        made_new_peak = (
            new_peak
            > prior_peak
        )

        for (
            trail_name,
            giveback,
        ) in TRAIL_GIVEBACKS.items():

            # Give back X% of profit from touch -> running peak.
            old_trail = (
                touch_prices[
                    :,
                    None
                ]
                + (
                    prior_peak
                    - touch_prices[
                        :,
                        None
                    ]
                )
                * (
                    1
                    - giveback
                )
            )

            # Guaranteed/resolved:
            # this trail already existed before candle opened.
            resolved_hit = (
                low_matrix
                <= old_trail
            )

            tightened_trail = (
                touch_prices[
                    :,
                    None
                ]
                + (
                    new_peak
                    - touch_prices[
                        :,
                        None
                    ]
                )
                * (
                    1
                    - giveback
                )
            )

            # Not below old trail, but would be below a trail that
            # only exists IF the new high occurred first.
            ambiguous_hit = (
                ~resolved_hit
                & made_new_peak
                & (
                    low_matrix
                    <= tightened_trail
                )
            )

            event_matrix = (
                resolved_hit
                | ambiguous_hit
            )

            has_event = (
                event_matrix.any(
                    axis=1
                )
            )

            first_event_offset = np.argmax(
                event_matrix,
                axis=1,
            )

            # argmax returns 0 when all False; only use where
            # has_event is True.
            rows_with_event = np.flatnonzero(
                has_event
            )

            global_positions = (
                chunk_positions[
                    rows_with_event
                ]
            )

            event_offsets = (
                first_event_offset[
                    rows_with_event
                ]
            )

            event_raw_indices = (
                chunk_start_indices[
                    rows_with_event
                ]
                + event_offsets
            )

            first_is_resolved = (
                resolved_hit[
                    rows_with_event,
                    event_offsets,
                ]
            )

            resolved_rows = (
                rows_with_event[
                    first_is_resolved
                ]
            )

            ambiguous_rows = (
                rows_with_event[
                    ~first_is_resolved
                ]
            )

            # ---------------------------------------------
            # Save all first-event metadata
            # ---------------------------------------------

            if len(
                rows_with_event
            ) > 0:

                unique_events.loc[
                    global_positions,
                    f"trail_{trail_name}_event_timestamp",
                ] = raw_times[
                    event_raw_indices
                ]

                unique_events.loc[
                    global_positions,
                    f"trail_{trail_name}_time_minutes",
                ] = (
                    event_offsets
                    + 1
                ).astype(
                    np.float64
                )

                event_prior_peaks = prior_peak[
                    rows_with_event,
                    event_offsets,
                ]

                event_old_trails = old_trail[
                    rows_with_event,
                    event_offsets,
                ]

                unique_events.loc[
                    global_positions,
                    f"trail_{trail_name}_peak_before_event_price",
                ] = event_prior_peaks

                unique_events.loc[
                    global_positions,
                    f"trail_{trail_name}_old_trail_price",
                ] = event_old_trails

                unique_events.loc[
                    global_positions,
                    f"trail_{trail_name}_old_locked_profit_pct",
                ] = (
                    (
                        event_old_trails
                        - touch_prices[
                            rows_with_event
                        ]
                    )
                    / touch_prices[
                        rows_with_event
                    ]
                    * 100
                )

            # ---------------------------------------------
            # Resolved trail hit
            # ---------------------------------------------

            if len(
                resolved_rows
            ) > 0:

                resolved_global = (
                    chunk_positions[
                        resolved_rows
                    ]
                )

                unique_events.loc[
                    resolved_global,
                    f"trail_{trail_name}_outcome",
                ] = "triggered_resolved"

            # ---------------------------------------------
            # Ambiguous same-candle tightening/hit
            # ---------------------------------------------

            if len(
                ambiguous_rows
            ) > 0:

                ambiguous_global = (
                    chunk_positions[
                        ambiguous_rows
                    ]
                )

                ambiguous_offsets = (
                    first_event_offset[
                        ambiguous_rows
                    ]
                )

                ambiguous_new_peaks = new_peak[
                    ambiguous_rows,
                    ambiguous_offsets,
                ]

                ambiguous_tightened_trails = tightened_trail[
                    ambiguous_rows,
                    ambiguous_offsets,
                ]

                unique_events.loc[
                    ambiguous_global,
                    f"trail_{trail_name}_outcome",
                ] = "ambiguous_same_candle"

                unique_events.loc[
                    ambiguous_global,
                    f"trail_{trail_name}_new_peak_same_candle_price",
                ] = ambiguous_new_peaks

                unique_events.loc[
                    ambiguous_global,
                    f"trail_{trail_name}_tightened_trail_same_candle_price",
                ] = ambiguous_tightened_trails

                unique_events.loc[
                    ambiguous_global,
                    f"trail_{trail_name}_tightened_locked_profit_same_candle_pct",
                ] = (
                    (
                        ambiguous_tightened_trails
                        - touch_prices[
                            ambiguous_rows
                        ]
                    )
                    / touch_prices[
                        ambiguous_rows
                    ]
                    * 100
                )

            # ---------------------------------------------
            # No event in available path
            # ---------------------------------------------

            no_event_rows = np.flatnonzero(
                ~has_event
            )

            if len(
                no_event_rows
            ) > 0:

                no_event_global = (
                    chunk_positions[
                        no_event_rows
                    ]
                )

                complete_no_event = (
                    available_lengths[
                        no_event_rows
                    ]
                    == OBSERVATION_MINUTES
                )

                complete_rows = (
                    no_event_rows[
                        complete_no_event
                    ]
                )

                incomplete_rows = (
                    no_event_rows[
                        ~complete_no_event
                    ]
                )

                if len(
                    complete_rows
                ) > 0:

                    unique_events.loc[
                        chunk_positions[
                            complete_rows
                        ],
                        f"trail_{trail_name}_outcome",
                    ] = "not_triggered_24h"

                if len(
                    incomplete_rows
                ) > 0:

                    unique_events.loc[
                        chunk_positions[
                            incomplete_rows
                        ],
                        f"trail_{trail_name}_outcome",
                    ] = "incomplete_unknown"

        print(
            f"    chunk "
            f"{min(chunk_start + CHUNK_SIZE, len(valid_positions)):,}"
            f"/{len(valid_positions):,}"
        )

    return unique_events


def build_statistics(
    df: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    activated = df[
        df[
            "trailing_activation_reached"
        ]
        .fillna(False)
        .astype(bool)
    ].copy()

    grouped = activated.groupby(
        [
            "asset",
            "timeframe",
            "average_type",
            "touch_zone",
        ],
        dropna=False,
        sort=True,
    )

    for (
        asset,
        timeframe,
        average_type,
        touch_zone,
    ), group in grouped:

        for (
            trail_name,
            giveback,
        ) in TRAIL_GIVEBACKS.items():

            outcome_column = (
                f"trail_{trail_name}_outcome"
            )

            locked_column = (
                f"trail_{trail_name}_old_locked_profit_pct"
            )

            time_column = (
                f"trail_{trail_name}_time_minutes"
            )

            outcomes = (
                group[
                    outcome_column
                ]
                .astype("string")
            )

            counts = (
                outcomes
                .value_counts(
                    dropna=False
                )
            )

            resolved = int(
                counts.get(
                    "triggered_resolved",
                    0,
                )
            )

            ambiguous = int(
                counts.get(
                    "ambiguous_same_candle",
                    0,
                )
            )

            not_triggered = int(
                counts.get(
                    "not_triggered_24h",
                    0,
                )
            )

            incomplete = int(
                counts.get(
                    "incomplete_unknown",
                    0,
                )
            )

            confirmed = (
                resolved
                + ambiguous
                + not_triggered
            )

            resolved_mask = (
                outcomes
                == "triggered_resolved"
            )

            resolved_locked = (
                group.loc[
                    resolved_mask,
                    locked_column,
                ]
                .dropna()
                .astype(float)
            )

            resolved_times = (
                group.loc[
                    resolved_mask,
                    time_column,
                ]
                .dropna()
                .astype(float)
            )

            rows.append(
                {
                    "asset": asset,
                    "timeframe": timeframe,
                    "average_type": average_type,
                    "touch_zone": touch_zone,
                    "trail_giveback_pct": (
                        giveback
                        * 100
                    ),
                    "activated_event_rows": len(
                        group
                    ),
                    "confirmed_count": confirmed,
                    "triggered_resolved_count": resolved,
                    "ambiguous_same_candle_count": ambiguous,
                    "not_triggered_24h_count": not_triggered,
                    "incomplete_unknown_count": incomplete,
                    "triggered_resolved_pct_confirmed": (
                        resolved
                        / confirmed
                        * 100
                        if confirmed > 0
                        else None
                    ),
                    "ambiguous_pct_confirmed": (
                        ambiguous
                        / confirmed
                        * 100
                        if confirmed > 0
                        else None
                    ),
                    "not_triggered_24h_pct_confirmed": (
                        not_triggered
                        / confirmed
                        * 100
                        if confirmed > 0
                        else None
                    ),
                    "median_locked_profit_pct_resolved": (
                        resolved_locked.median()
                        if len(
                            resolved_locked
                        ) > 0
                        else None
                    ),
                    "p25_locked_profit_pct_resolved": (
                        resolved_locked.quantile(
                            0.25
                        )
                        if len(
                            resolved_locked
                        ) > 0
                        else None
                    ),
                    "p75_locked_profit_pct_resolved": (
                        resolved_locked.quantile(
                            0.75
                        )
                        if len(
                            resolved_locked
                        ) > 0
                        else None
                    ),
                    "median_time_to_trail_event_minutes": (
                        resolved_times.median()
                        if len(
                            resolved_times
                        ) > 0
                        else None
                    ),
                }
            )

    return pd.DataFrame(
        rows
    )


def process_dataset(
    symbol: str,
    timeframe: str,
):

    print(
        f"\nProcessing {symbol} {timeframe}"
    )

    events = load_events(
        symbol,
        timeframe,
    )

    raw = load_raw(
        symbol
    )

    original_rows = len(
        events
    )

    # Compute once per underlying touch / activation.
    unique_events = (
        events[
            [
                "timestamp",
                "price",
                "target_2_5_price",
                "target_2_5_first_hit_timestamp",
                "trailing_activation_reached",
                "trailing_activation_timestamp",
                "trailing_activation_price",
                "post_activation_start_timestamp",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    print(
        f"  Event rows: "
        f"{len(events):,}"
    )

    print(
        f"  Unique touch candles/prices: "
        f"{len(unique_events):,}"
    )

    print(
        f"  Activated: "
        f"{int(unique_events['trailing_activation_reached'].fillna(False).sum()):,}"
    )

    unique_events = (
        simulate_trailing_for_unique_events(
            unique_events,
            raw,
        )
    )

    new_columns = [
        column
        for column in unique_events.columns
        if column not in [
            "timestamp",
            "price",
            "target_2_5_price",
            "target_2_5_first_hit_timestamp",
            "trailing_activation_reached",
            "trailing_activation_timestamp",
            "trailing_activation_price",
            "post_activation_start_timestamp",
        ]
    ]

    output = events.merge(
        unique_events[
            [
                "timestamp",
                "price",
                "target_2_5_price",
                "target_2_5_first_hit_timestamp",
                "trailing_activation_reached",
                "trailing_activation_timestamp",
                "trailing_activation_price",
                "post_activation_start_timestamp",
                *new_columns,
            ]
        ],
        on=[
            "timestamp",
            "price",
            "target_2_5_price",
            "target_2_5_first_hit_timestamp",
            "trailing_activation_reached",
            "trailing_activation_timestamp",
            "trailing_activation_price",
            "post_activation_start_timestamp",
        ],
        how="left",
        validate="many_to_one",
    )

    if len(
        output
    ) != original_rows:

        raise ValueError(
            f"{symbol} {timeframe}: "
            f"row count changed from "
            f"{original_rows:,} "
            f"to {len(output):,}"
        )

    output["asset"] = symbol
    output["timeframe"] = timeframe

    output_file = (
        RESEARCH_DIR
        / symbol
        / (
            f"{symbol}_{timeframe}"
            f"_touch_events_with_trailing_research.parquet"
        )
    )

    output.to_parquet(
        output_file,
        index=False,
    )

    print(
        f"Saved: {output_file}"
    )

    # Print overall diagnostic counts.
    unique_activated = output[
        output[
            "trailing_activation_reached"
        ]
        .fillna(False)
        .astype(bool)
    ].drop_duplicates(
        subset=[
            "timestamp",
            "price",
        ]
    )

    for trail_name in TRAIL_GIVEBACKS:

        counts = (
            unique_activated[
                f"trail_{trail_name}_outcome"
            ]
            .value_counts(
                dropna=False
            )
        )

        print(
            f"  Trail {trail_name}% giveback:"
        )

        print(
            f"    resolved: "
            f"{int(counts.get('triggered_resolved', 0)):,}"
        )

        print(
            f"    ambiguous: "
            f"{int(counts.get('ambiguous_same_candle', 0)):,}"
        )

        print(
            f"    not triggered 24h: "
            f"{int(counts.get('not_triggered_24h', 0)):,}"
        )

        print(
            f"    incomplete: "
            f"{int(counts.get('incomplete_unknown', 0)):,}"
        )

    return output


def main():

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs = []

    for symbol in SYMBOLS:

        for timeframe in TIMEFRAMES:

            output = process_dataset(
                symbol,
                timeframe,
            )

            outputs.append(
                output
            )

    print(
        "\nBuilding setup-specific trailing statistics..."
    )

    combined = pd.concat(
        outputs,
        ignore_index=True,
    )

    stats = build_statistics(
        combined
    )

    stats = (
        stats
        .sort_values(
            [
                "asset",
                "timeframe",
                "average_type",
                "touch_zone",
                "trail_giveback_pct",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    output_stats = (
        RESULTS_DIR
        / "trailing_research_statistics.csv"
    )

    stats.to_csv(
        output_stats,
        index=False,
    )

    print(
        f"\nSaved statistics:"
    )

    print(
        output_stats
    )

    print(
        f"\nStatistic rows: "
        f"{len(stats):,}"
    )

    # ---------------------------------------------------------
    # Display main candidate only for readability.
    # Full CSV contains ALL BTC / ETH / SOL setups.
    # ---------------------------------------------------------

    candidate = stats[
        (stats["asset"] == "SOLUSDT")
        & (
            stats["average_type"]
            == "15d"
        )
        & (
            stats["touch_zone"]
            == 0.5
        )
    ]

    print(
        "\n"
        + "=" * 120
    )

    print(
        "SOLUSDT | 15D | 0.5% TOUCH ZONE"
    )

    print(
        "TRAILING GIVEBACK RESEARCH"
    )

    print(
        "=" * 120
    )

    print(
        candidate[
            [
                "asset",
                "timeframe",
                "trail_giveback_pct",
                "activated_event_rows",
                "triggered_resolved_pct_confirmed",
                "ambiguous_pct_confirmed",
                "not_triggered_24h_pct_confirmed",
                "median_locked_profit_pct_resolved",
                "median_time_to_trail_event_minutes",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
