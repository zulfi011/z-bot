from pathlib import Path

import numpy as np
import pandas as pd


TABLES_DIR = Path("results/tables")
REPORTS_DIR = Path("results/reports")

SUMMARY_FILE = (
    TABLES_DIR
    / "stage1_configuration_summary.csv"
)

AVERAGE_FILE = (
    TABLES_DIR
    / "average_overall_summary.csv"
)

TIMEFRAME_FILE = (
    TABLES_DIR
    / "timeframe_comparison_overall.csv"
)

ASSET_FILE = (
    TABLES_DIR
    / "asset_comparison_overall.csv"
)

REGIME_FILE = (
    TABLES_DIR
    / "regime_primary_setup_comparison.csv"
)

OUTPUT_FILE = (
    REPORTS_DIR
    / "stage1_research_report.md"
)


HORIZONS = [
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "24h",
]


def load_csv(path: Path) -> pd.DataFrame:

    if not path.exists():

        raise FileNotFoundError(
            f"Missing required file: {path}"
        )

    return pd.read_csv(
        path
    )


def fmt_pct(value, digits=3):

    if pd.isna(value):
        return "NA"

    return (
        f"{float(value):.{digits}f}%"
    )


def fmt_num(value, digits=3):

    if pd.isna(value):
        return "NA"

    return (
        f"{float(value):.{digits}f}"
    )


def fmt_int(value):

    if pd.isna(value):
        return "NA"

    return (
        f"{int(value):,}"
    )


def markdown_table(
    df: pd.DataFrame,
) -> list[str]:

    if df.empty:
        return [
            "No data available."
        ]

    headers = [
        str(column)
        for column in df.columns
    ]

    rows = []

    rows.append(
        "| "
        + " | ".join(
            headers
        )
        + " |"
    )

    rows.append(
        "| "
        + " | ".join(
            "---"
            for _ in headers
        )
        + " |"
    )

    for _, row in df.iterrows():

        values = [
            str(
                row[column]
            )
            for column in headers
        ]

        rows.append(
            "| "
            + " | ".join(
                values
            )
            + " |"
        )

    return rows


def main():

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # Load Stage 1 outputs
    # ---------------------------------------------------------

    summary = load_csv(
        SUMMARY_FILE
    )

    average_summary = load_csv(
        AVERAGE_FILE
    )

    timeframe_summary = load_csv(
        TIMEFRAME_FILE
    )

    asset_summary = load_csv(
        ASSET_FILE
    )

    regime_primary = load_csv(
        REGIME_FILE
    )

    # ---------------------------------------------------------
    # Basic validation
    # ---------------------------------------------------------

    if len(summary) != 81:

        raise ValueError(
            "Expected 81 Stage 1 configurations, "
            f"found {len(summary)}"
        )

    keys = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
    ]

    if summary[
        keys
    ].duplicated().any():

        raise ValueError(
            "Duplicate configurations found "
            "in Stage 1 summary."
        )

    # ---------------------------------------------------------
    # Validate forward-return columns
    # ---------------------------------------------------------

    required_forward_columns = []

    for horizon in HORIZONS:

        required_forward_columns += [
            f"return_{horizon}_valid_count",
            f"return_{horizon}_median_pct",
            f"return_{horizon}_mean_pct",
        ]

    missing_forward_columns = [
        column
        for column in required_forward_columns
        if column not in summary.columns
    ]

    if missing_forward_columns:

        raise ValueError(
            "Missing forward-return columns: "
            + str(
                missing_forward_columns
            )
        )

    if summary[
        required_forward_columns
    ].isna().any().any():

        raise ValueError(
            "Missing forward-return values found."
        )

    # ---------------------------------------------------------
    # Primary Stage 1 research candidate
    # ---------------------------------------------------------

    primary = summary[
        (
            summary[
                "asset"
            ]
            == "SOLUSDT"
        )
        &
        (
            summary[
                "timeframe"
            ]
            == "5m"
        )
        &
        (
            summary[
                "average_type"
            ]
            .astype(str)
            .str.lower()
            == "15d"
        )
        &
        (
            np.isclose(
                summary[
                    "touch_zone"
                ]
                .astype(float),
                0.5,
            )
        )
    ]

    if len(primary) != 1:

        raise ValueError(
            "Expected exactly one "
            "SOLUSDT / 5m / 15D / 0.5% "
            "configuration."
        )

    primary = primary.iloc[
        0
    ]

    # ---------------------------------------------------------
    # Forward-return table for primary setup
    # ---------------------------------------------------------

    forward_rows = []

    for horizon in HORIZONS:

        forward_rows.append(
            {
                "Horizon":
                    horizon,
                "Valid events":
                    fmt_int(
                        primary[
                            f"return_{horizon}_valid_count"
                        ]
                    ),
                "Median return":
                    fmt_pct(
                        primary[
                            f"return_{horizon}_median_pct"
                        ]
                    ),
                "Mean return":
                    fmt_pct(
                        primary[
                            f"return_{horizon}_mean_pct"
                        ]
                    ),
            }
        )

    primary_forward_table = (
        pd.DataFrame(
            forward_rows
        )
    )

    # ---------------------------------------------------------
    # Touch-zone descriptive comparison
    #
    # This is deliberately descriptive.
    # We do NOT create another simplistic winner score.
    # ---------------------------------------------------------

    zone_summary = (
        summary
        .groupby(
            "touch_zone",
            observed=True,
        )
        .agg(
            configurations=(
                "asset",
                "size",
            ),
            median_reach_probability_pct=(
                "reach_probability_pct",
                "median",
            ),
            median_mae_24h_pct=(
                "mae_24h_median_pct",
                "median",
            ),
            median_mfe_24h_pct=(
                "mfe_24h_median_pct",
                "median",
            ),
            median_mfe_mae_ratio=(
                "median_mfe_mae_ratio",
                "median",
            ),
            median_target_first_2_5_pct=(
                "target_2_5_first_vs_stop_2_5_pct",
                "median",
            ),
            median_post_activation_upside_pct=(
                "post_activation_median_extra_upside_24h_pct",
                "median",
            ),
        )
        .reset_index()
    )

    # ---------------------------------------------------------
    # Create readable comparison tables
    # ---------------------------------------------------------

    average_report = (
        average_summary[
            [
                "average_type",
                "reach_probability_pct",
                "mae_24h_median_pct",
                "mfe_24h_median_pct",
                "median_mfe_mae_ratio",
                "target_2_5_first_vs_stop_2_5_pct",
                "mean_metric_rank",
            ]
        ]
        .copy()
    )

    average_report.columns = [
        "Average",
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "MFE/MAE",
        "Target-first",
        "Mean metric rank",
    ]

    for column in [
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "Target-first",
    ]:

        average_report[
            column
        ] = (
            average_report[
                column
            ]
            .map(
                lambda x:
                fmt_pct(
                    x,
                    2,
                )
            )
        )

    average_report[
        "MFE/MAE"
    ] = (
        average_report[
            "MFE/MAE"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                3,
            )
        )
    )

    average_report[
        "Mean metric rank"
    ] = (
        average_report[
            "Mean metric rank"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                2,
            )
        )
    )

    # ---------------------------------------------------------

    timeframe_report = (
        timeframe_summary[
            [
                "timeframe",
                "reach_probability_pct",
                "mae_24h_median_pct",
                "mfe_24h_median_pct",
                "median_mfe_mae_ratio",
                "target_2_5_first_vs_stop_2_5_pct",
                "event_count",
                "mean_metric_rank",
            ]
        ]
        .copy()
    )

    timeframe_report.columns = [
        "Timeframe",
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "MFE/MAE",
        "Target-first",
        "Median events",
        "Mean metric rank",
    ]

    for column in [
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "Target-first",
    ]:

        timeframe_report[
            column
        ] = (
            timeframe_report[
                column
            ]
            .map(
                lambda x:
                fmt_pct(
                    x,
                    2,
                )
            )
        )

    timeframe_report[
        "MFE/MAE"
    ] = (
        timeframe_report[
            "MFE/MAE"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                3,
            )
        )
    )

    timeframe_report[
        "Median events"
    ] = (
        timeframe_report[
            "Median events"
        ]
        .map(
            fmt_int
        )
    )

    timeframe_report[
        "Mean metric rank"
    ] = (
        timeframe_report[
            "Mean metric rank"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                2,
            )
        )
    )

    # ---------------------------------------------------------

    asset_report = (
        asset_summary[
            [
                "asset",
                "reach_probability_pct",
                "mae_24h_median_pct",
                "mfe_24h_median_pct",
                "median_mfe_mae_ratio",
                "target_2_5_first_vs_stop_2_5_pct",
                "post_activation_median_extra_upside_24h_pct",
                "trail30_median_realized_return_pct",
            ]
        ]
        .copy()
    )

    asset_report.columns = [
        "Asset",
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "MFE/MAE",
        "Target-first",
        "Post-activation upside",
        "30% trail median",
    ]

    for column in [
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "Target-first",
        "Post-activation upside",
        "30% trail median",
    ]:

        asset_report[
            column
        ] = (
            asset_report[
                column
            ]
            .map(
                lambda x:
                fmt_pct(
                    x,
                    2,
                )
            )
        )

    asset_report[
        "MFE/MAE"
    ] = (
        asset_report[
            "MFE/MAE"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                3,
            )
        )
    )

    # ---------------------------------------------------------
    # Touch-zone table formatting
    # ---------------------------------------------------------

    zone_report = (
        zone_summary.copy()
    )

    zone_report.columns = [
        "Touch zone",
        "Configurations",
        "Median +2.5% reach",
        "Median MAE",
        "Median MFE",
        "Median MFE/MAE",
        "Median target-first",
        "Median post-activation upside",
    ]

    zone_report[
        "Touch zone"
    ] = (
        zone_report[
            "Touch zone"
        ]
        .map(
            lambda x:
            f"±{float(x):.1f}%"
        )
    )

    for column in [
        "Median +2.5% reach",
        "Median MAE",
        "Median MFE",
        "Median target-first",
        "Median post-activation upside",
    ]:

        zone_report[
            column
        ] = (
            zone_report[
                column
            ]
            .map(
                lambda x:
                fmt_pct(
                    x,
                    2,
                )
            )
        )

    zone_report[
        "Median MFE/MAE"
    ] = (
        zone_report[
            "Median MFE/MAE"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                3,
            )
        )
    )

    # ---------------------------------------------------------
    # Regime table
    # ---------------------------------------------------------

    regime_report = (
        regime_primary[
            [
                "market_regime",
                "event_count",
                "median_return_24h_pct",
                "reach_2_5_probability_pct",
                "mae_24h_median_pct",
                "mfe_24h_median_pct",
                "median_mfe_mae_ratio",
                "target_first_decisive_pct",
                "post_activation_median_extra_upside_24h_pct",
                "trail30_median_locked_profit_pct",
            ]
        ]
        .copy()
    )

    regime_report.columns = [
        "Regime",
        "Events",
        "24h median return",
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "MFE/MAE",
        "Target-first decisive",
        "Post-activation upside",
        "30% trail locked",
    ]

    regime_report[
        "Regime"
    ] = (
        regime_report[
            "Regime"
        ]
        .astype(str)
        .str.title()
    )

    regime_report[
        "Events"
    ] = (
        regime_report[
            "Events"
        ]
        .map(
            fmt_int
        )
    )

    for column in [
        "24h median return",
        "+2.5% reach",
        "Median MAE",
        "Median MFE",
        "Target-first decisive",
        "Post-activation upside",
        "30% trail locked",
    ]:

        regime_report[
            column
        ] = (
            regime_report[
                column
            ]
            .map(
                lambda x:
                fmt_pct(
                    x,
                    2,
                )
            )
        )

    regime_report[
        "MFE/MAE"
    ] = (
        regime_report[
            "MFE/MAE"
        ]
        .map(
            lambda x:
            fmt_num(
                x,
                3,
            )
        )
    )

    # ---------------------------------------------------------
    # Build report
    # ---------------------------------------------------------

    lines = []

    lines.append(
        "# V1 Stage 1 Research Report"
    )

    lines.append("")

    lines.append(
        "## 1. Research Objective"
    )

    lines.append("")

    lines.append(
        "Stage 1 investigated whether price interactions "
        "with completed-day 7D, 15D and 30D averages show "
        "repeatable forward behavior across BTCUSDT, "
        "ETHUSDT and SOLUSDT."
    )

    lines.append("")

    lines.append(
        "This is historical research only. "
        "Stage 1 does not constitute a live trading strategy."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Scope
    # ---------------------------------------------------------

    lines.append(
        "## 2. Experiment Scope"
    )

    lines.append("")

    lines.append(
        "- Exchange: Binance"
    )

    lines.append(
        "- Market: Spot"
    )

    lines.append(
        "- Assets: BTCUSDT, ETHUSDT, SOLUSDT"
    )

    lines.append(
        "- Historical base data: 1-minute candles"
    )

    lines.append(
        "- Derived timeframes: 1m, 3m, 5m"
    )

    lines.append(
        "- Averages: 7D, 15D, 30D"
    )

    lines.append(
        "- Touch zones: ±0.5%, ±1.0%, ±1.5%"
    )

    lines.append(
        "- Configurations per asset: 27"
    )

    lines.append(
        "- Total configurations: 81"
    )

    lines.append("")

    lines.append(
        "All averages use completed previous daily closes, "
        "so the average calculations do not use future daily data."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------

    lines.append(
        "## 3. Metrics Evaluated"
    )

    lines.append("")

    lines.append(
        "- Forward returns at 5m, 15m, 30m, 1h, 4h and 24h"
    )

    lines.append(
        "- +0.5%, +1%, +1.5%, +2%, +2.5%, +3% and +5% target reach"
    )

    lines.append(
        "- Maximum adverse excursion (MAE)"
    )

    lines.append(
        "- Maximum favorable excursion (MFE)"
    )

    lines.append(
        "- MFE/MAE balance"
    )

    lines.append(
        "- Target-vs-stop first-hit ordering"
    )

    lines.append(
        "- Post +2.5% activation continuation"
    )

    lines.append(
        "- Profit-giveback trailing behavior"
    )

    lines.append(
        "- Bullish, Neutral and Bearish market regimes"
    )

    lines.append("")

    # ---------------------------------------------------------
    # Event count definition
    # ---------------------------------------------------------

    lines.append(
        "## 4. Event Count Definitions"
    )

    lines.append("")

    lines.append(
        "`forward_return_total_event_count` represents "
        "all touch events available for forward-return analysis."
    )

    lines.append("")

    lines.append(
        "`event_count` in the Stage 1 configuration summary "
        "represents observations with a valid complete 24-hour "
        "research window."
    )

    lines.append("")

    lines.append(
        "For all 81 configurations, `event_count` matches "
        "`return_24h_valid_count`."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Forward returns
    # ---------------------------------------------------------

    lines.append(
        "## 5. Forward Returns"
    )

    lines.append("")

    lines.append(
        "Forward-return statistics are available independently "
        "for every one of the 81 configurations."
    )

    lines.append("")

    lines.append(
        "### Current leading research candidate"
    )

    lines.append("")

    lines.append(
        "SOLUSDT / 5m / 15D / ±0.5%"
    )

    lines.append("")

    lines.extend(
        markdown_table(
            primary_forward_table
        )
    )

    lines.append("")

    lines.append(
        "Forward returns are descriptive outcomes after a touch. "
        "They are not equivalent to realized trade returns because "
        "Stage 1 does not yet define complete entry and exit state."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Average
    # ---------------------------------------------------------

    lines.append(
        "## 6. Average Comparison"
    )

    lines.append("")

    lines.extend(
        markdown_table(
            average_report
        )
    )

    lines.append("")

    lines.append(
        "**Conclusion:** 15D remains the strongest supported "
        "primary average. It provides the strongest overall "
        "balance rather than merely the largest raw movement."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Timeframe
    # ---------------------------------------------------------

    lines.append(
        "## 7. Timeframe Comparison"
    )

    lines.append("")

    lines.extend(
        markdown_table(
            timeframe_report
        )
    )

    lines.append("")

    lines.append(
        "**Conclusion:** 1m, 3m and 5m behave very similarly. "
        "The evidence does not justify claiming that 5m is "
        "statistically superior."
    )

    lines.append("")

    lines.append(
        "5m remains the primary operational candidate because "
        "it substantially reduces repeated touch observations "
        "while retaining nearly the same measured behavior."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Asset
    # ---------------------------------------------------------

    lines.append(
        "## 8. Asset Comparison"
    )

    lines.append("")

    lines.extend(
        markdown_table(
            asset_report
        )
    )

    lines.append("")

    lines.append(
        "**Conclusion:** SOLUSDT is the strongest opportunity "
        "candidate in Stage 1, particularly for target reach, "
        "MFE and post-activation movement."
    )

    lines.append("")

    lines.append(
        "SOLUSDT is not universally the safest or best asset. "
        "BTCUSDT shows materially smaller downside excursions, "
        "while ETHUSDT remains an important secondary validation asset."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Zone
    # ---------------------------------------------------------

    lines.append(
        "## 9. Touch-Zone Comparison"
    )

    lines.append("")

    lines.extend(
        markdown_table(
            zone_report
        )
    )

    lines.append("")

    lines.append(
        "**Conclusion:** ±0.5% remains the leading touch-zone "
        "candidate, particularly for the SOL / 15D setup, "
        "but it is not treated as a finalized trading threshold."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Primary setup
    # ---------------------------------------------------------

    lines.append(
        "## 10. Current Leading Research Configuration"
    )

    lines.append("")

    lines.append(
        "- Asset: SOLUSDT"
    )

    lines.append(
        "- Average: 15D"
    )

    lines.append(
        "- Timeframe: 5m"
    )

    lines.append(
        "- Touch zone: ±0.5%"
    )

    lines.append("")

    lines.append(
        f"- Complete 24h events: "
        f"{fmt_int(primary['event_count'])}"
    )

    lines.append(
        f"- All forward-return touch events: "
        f"{fmt_int(primary['forward_return_total_event_count'])}"
    )

    lines.append(
        f"- +2.5% reach probability: "
        f"{fmt_pct(primary['reach_probability_pct'])}"
    )

    lines.append(
        f"- Median time to +2.5%: "
        f"{fmt_num(primary['median_time_to_target_minutes'], 1)} minutes"
    )

    lines.append(
        f"- Median 24h MAE: "
        f"{fmt_pct(primary['mae_24h_median_pct'])}"
    )

    lines.append(
        f"- Median 24h MFE: "
        f"{fmt_pct(primary['mfe_24h_median_pct'])}"
    )

    lines.append(
        f"- Median MFE/MAE ratio: "
        f"{fmt_num(primary['median_mfe_mae_ratio'])}"
    )

    lines.append(
        f"- +2.5% target before -2.5% stop, "
        f"all-confirmed basis: "
        f"{fmt_pct(primary['target_2_5_first_vs_stop_2_5_pct'])}"
    )

    lines.append(
        f"- Median post-activation extra upside: "
        f"{fmt_pct(primary['post_activation_median_extra_upside_24h_pct'])}"
    )

    lines.append(
        f"- 30% profit-giveback median resolved return: "
        f"{fmt_pct(primary['trail30_median_realized_return_pct'])}"
    )

    lines.append("")

    lines.append(
        "This is a leading hypothesis configuration, "
        "not a completed strategy."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Regime
    # ---------------------------------------------------------

    lines.append(
        "## 11. Market-Regime Findings"
    )

    lines.append("")

    lines.append(
        "SOLUSDT / 5m / 15D / ±0.5%:"
    )

    lines.append("")

    lines.extend(
        markdown_table(
            regime_report
        )
    )

    lines.append("")

    lines.append(
        "**Neutral:** strongest balanced behavior, including "
        "better MFE/MAE balance, target-first behavior and "
        "post-activation continuation."
    )

    lines.append("")

    lines.append(
        "**Bearish:** strongest rebound/target-reach behavior "
        "but accompanied by larger adverse excursions."
    )

    lines.append("")

    lines.append(
        "**Bullish:** weaker risk/reward balance for this "
        "specific average-touch hypothesis."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Trailing
    # ---------------------------------------------------------

    lines.append(
        "## 12. +2.5% Activation and Trailing Research"
    )

    lines.append("")

    lines.append(
        "+2.5% remains a useful Stage 2 activation candidate."
    )

    lines.append("")

    lines.append(
        "A 30% giveback of accumulated profit remains the "
        "most practical trailing candidate identified in Stage 1: "
        "it greatly reduces the same-candle ambiguity seen with "
        "tighter trails while retaining meaningful locked profit."
    )

    lines.append("")

    lines.append(
        "It is not yet proven to be the mathematically optimal exit."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Interpretation
    # ---------------------------------------------------------

    lines.append(
        "## 13. Interpretation of the Asset Ranking"
    )

    lines.append("")

    lines.append(
        "Several Stage 1 opportunity metrics are related to one "
        "another. Target reach, MFE and target-first behavior all "
        "partly reflect the strength and volatility of subsequent "
        "price movement."
    )

    lines.append("")

    lines.append(
        "Therefore SOLUSDT's multiple metric wins should not be "
        "treated as completely independent confirmations."
    )

    lines.append("")

    lines.append(
        "The correct interpretation is that SOLUSDT is the "
        "strongest opportunity candidate found by Stage 1, "
        "while its higher downside excursion remains an important "
        "risk consideration for Stage 2."
    )

    lines.append("")

    # ---------------------------------------------------------
    # Limitations
    # ---------------------------------------------------------

    lines.append(
        "## 14. Important Limitations"
    )

    lines.append("")

    limitations = [
        (
            "Touch-event observations are not independent trades."
        ),
        (
            "Consecutive candles can represent the same underlying "
            "market interaction."
        ),
        (
            "The ±0.5%, ±1.0% and ±1.5% touch zones are nested "
            "and therefore correlated."
        ),
        (
            "1m, 3m and 5m represent heavily overlapping "
            "underlying market behavior."
        ),
        (
            "Several opportunity metrics are correlated and "
            "should not be treated as independent evidence."
        ),
        (
            "Same-candle OHLC ambiguity prevents exact intraminute "
            "ordering in some trailing and first-hit situations."
        ),
        (
            "Stage 1 does not yet model actual strategy state, "
            "signal deduplication or overlapping positions."
        ),
        (
            "Stage 1 does not yet model fees, slippage, position "
            "sizing, capital allocation or portfolio exposure."
        ),
        (
            "The current results are based on the researched "
            "historical period and still require robust strategy "
            "backtesting and out-of-sample validation."
        ),
    ]

    for limitation in limitations:

        lines.append(
            f"- {limitation}"
        )

    lines.append("")

    # ---------------------------------------------------------
    # Stage 2 candidates
    # ---------------------------------------------------------

    lines.append(
        "## 15. Stage 2 Research Candidates"
    )

    lines.append("")

    lines.append(
        "- Primary opportunity asset: SOLUSDT"
    )

    lines.append(
        "- Secondary validation asset: ETHUSDT"
    )

    lines.append(
        "- Lower-volatility reference asset: BTCUSDT"
    )

    lines.append(
        "- Primary average: 15D"
    )

    lines.append(
        "- Operational timeframe candidate: 5m"
    )

    lines.append(
        "- Leading touch-zone candidate: ±0.5%"
    )

    lines.append(
        "- Preferred balanced regime candidate: Neutral"
    )

    lines.append(
        "- Higher-risk rebound regime: Bearish"
    )

    lines.append(
        "- Activation candidate: +2.5%"
    )

    lines.append(
        "- Trailing candidate: 30% profit giveback"
    )

    lines.append("")

    # ---------------------------------------------------------
    # Final conclusion
    # ---------------------------------------------------------

    lines.append(
        "## 16. Final Stage 1 Conclusion"
    )

    lines.append("")

    lines.append(
        "Stage 1 provides sufficient evidence to continue "
        "researching the average-touch hypothesis."
    )

    lines.append("")

    lines.append(
        "The strongest direction identified is SOLUSDT interacting "
        "with the 15D completed-close average. A ±0.5% touch zone "
        "and 5-minute operational timeframe are the leading practical "
        "candidates, particularly in Neutral market structure."
    )

    lines.append("")

    lines.append(
        "However, the evidence does not establish "
        "SOL / 15D / 5m / ±0.5% as a finished or universally "
        "optimal strategy."
    )

    lines.append("")

    lines.append(
        "Stage 2 must convert these research observations into "
        "actual trade-state rules and test whether the apparent "
        "edge survives deduplication, entry/exit rules, fees, "
        "slippage and out-of-sample evaluation."
    )

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    OUTPUT_FILE.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    print(
        "\n"
        + "=" * 90
    )

    print(
        "CORRECTED STAGE 1 RESEARCH REPORT"
    )

    print(
        "=" * 90
    )

    print(
        "\nConfigurations:",
        len(
            summary
        ),
    )

    print(
        "Summary columns:",
        len(
            summary.columns
        ),
    )

    print(
        "Forward-return metric columns:",
        len(
            required_forward_columns
        ),
    )

    print(
        "Missing forward-return values:",
        int(
            summary[
                required_forward_columns
            ]
            .isna()
            .sum()
            .sum()
        ),
    )

    print(
        "\nPrimary configuration:"
    )

    print(
        "SOLUSDT / 5m / 15D / ±0.5%"
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()