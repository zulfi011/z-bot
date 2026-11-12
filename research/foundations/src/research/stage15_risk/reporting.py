"""Write the Step 4 report and compact reference figures."""

import os

import numpy as np
import pandas as pd


def table(frame: pd.DataFrame) -> str:
    lines = [
        "| " + " | ".join(frame.columns) + " |",
        "|" + "|".join(["---"] * len(frame.columns)) + "|",
    ]
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            if pd.isna(value):
                cells.append("—")
            elif isinstance(value, (float, np.floating)):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(path, summary, screen, cross_grid, protected_count, candidate_rows):
    reference = summary.loc[
        summary.asset.eq("SOLUSDT")
        & summary.timeframe.eq("5m")
        & summary.average_type.eq("15d")
        & summary.touch_zone.eq(0.5)
        & summary.policy.eq("first_touch_0m")
        & summary.segment.eq("all_entries")
        & summary.period.isin(["all", "earlier", "later"])
    ].copy()
    reference["period"] = pd.Categorical(
        reference.period, categories=["all", "earlier", "later"], ordered=True
    )
    reference = reference.sort_values(["period", "stop_pct"], na_position="first")
    ref_columns = [
        "period",
        "protection",
        "entries",
        "stop_hit_pct",
        "return_24h_mean_pct",
        "return_24h_median_pct",
        "return_24h_p10_pct",
        "expected_shortfall_10_pct",
        "mean_change_vs_hold_pp",
        "stopped_then_24h_positive_pct",
        "stopped_before_later_target_pct",
    ]
    bullish = summary.loc[
        summary.asset.eq("SOLUSDT")
        & summary.timeframe.eq("5m")
        & summary.average_type.eq("15d")
        & summary.touch_zone.eq(0.5)
        & summary.policy.eq("first_touch_0m")
        & summary.segment.eq("bullish_regime")
        & summary.period.eq("all")
    ].sort_values("stop_pct", na_position="first")
    stable = screen.loc[screen.stability_screen]
    stable_columns = [
        "asset",
        "timeframe",
        "average_type",
        "touch_zone",
        "policy",
        "segment",
        "protection",
        "entries_earlier",
        "entries_later",
        "mean_change_vs_hold_pp_earlier",
        "mean_change_vs_hold_pp_later",
        "expected_shortfall_10_pct_later",
        "stopped_then_24h_positive_pct_later",
        "positive_block_ci_both",
    ]
    cross = cross_grid.loc[
        cross_grid.policy.eq("first_touch_0m")
        & cross_grid.segment.eq("all_entries")
        & cross_grid.period.eq("later")
    ].sort_values("stop_pct")
    cross_columns = [
        "protection",
        "configurations",
        "median_stop_hit_pct",
        "configs_mean_improved",
        "median_mean_change_vs_hold_pp",
        "median_stopped_then_positive_pct",
        "median_stopped_before_later_target_pct",
        "median_expected_shortfall_10_pct",
    ]

    reference_all = reference.loc[reference.period.eq("all")]
    best_mean = reference_all.loc[reference_all.return_24h_mean_pct.idxmax()]
    tight = reference_all.loc[reference_all.protection.eq("stop_0.5")].iloc[0]
    moderate = reference_all.loc[reference_all.protection.eq("stop_2")].iloc[0]
    report = [
        "# Stage 1.5 Step 4 — Downside Protection",
        "",
        "## Scope and execution",
        "",
        "This step tests fixed long-position stops across all 81 configurations for the retained first-touch entry "
        "and the secondary 30-minute bullish-candle entry. Stops are 0.5%, 1%, 1.5%, 2%, 2.5%, 3%, 4%, and 5% "
        "below the actual inherited entry price. No market condition is adopted as a filter; bullish-regime results "
        "are retained as a descriptive secondary segment.",
        "",
        "Each stop watches raw 1-minute lows from the entry minute through minute 1,440. A triggered stop fills at "
        "the worse of its threshold and that minute's open, which accounts for a gap through the stop. An untriggered "
        "trade exits at the existing minute-1,440 close. Fees, slippage beyond gap handling, overlapping positions, "
        "profit exits, and trailing rules are outside this step.",
        "",
        "## Reference setup: SOL / 15D / 5m / ±0.5%, first-touch entry",
        "",
        table(reference[ref_columns]),
        "",
        "`stopped_then_24h_positive_pct` is the share of stopped trades whose original 24-hour close was positive. "
        "`stopped_before_later_target_pct` is the share stopped before price later reached +2.5%. These expose the "
        "opportunity cost of protection. Same-minute target/stop order remains explicitly ambiguous.",
        "",
        "## Reference bullish-regime segment — full history",
        "",
        table(bullish[ref_columns[1:]]),
        "",
        "This segment is descriptive because Step 3 did not validate a hard regime filter.",
        "",
        "## Cross-grid later-period evidence: first-touch entry",
        "",
        table(cross[cross_columns]),
        "",
        "The configurations overlap in episodes and price paths, so counts measure consistency across research setups, "
        "not 81 independent experiments.",
        "",
        "## Stability screen",
        "",
        f"{len(stable)} stop/setup/entry/segment combinations pass the prespecified descriptive screen: at least 100 "
        "entries in each period, positive protected mean return in both periods, higher mean return than holding in "
        "both periods, and controlled worst-decile loss in both periods. The first 15 are shown.",
        "",
        table(stable[stable_columns].head(15)),
        "",
        "Block intervals resample seven-day calendar blocks and are exploratory. They are not adjusted for the many "
        "stop/setup comparisons. A positive interval in both periods is stronger descriptive evidence, not proof of "
        "a tradable edge.",
        "",
        "## Validation and preservation",
        "",
        f"The run evaluates {candidate_rows:,} inherited episode-entry rows. Entry prices and 24-hour hold returns are "
        "matched back to Step 3, and deterministic samples replay every stop trigger, fill, time, protected return, "
        "and +2.5%-target ordering directly from raw candles. Raw grids, completeness, unique keys, Parquet/CSV round "
        "trips, and summary cardinality are checked.",
        "",
        f"Before/after SHA-256 confirms {protected_count} prior files are unchanged. All new artifacts are isolated "
        "under Step 4 paths.",
        "",
        "## Step 4 decision",
        "",
        f"For the reference setup, the highest full-history mean among the tested choices is `{best_mean.protection}` "
        f"at {best_mean.return_24h_mean_pct:+.3f}%, compared with the no-stop hold result. A 0.5% stop is hit "
        f"{tight.stop_hit_pct:.1f}% of the time; {tight.stopped_then_24h_positive_pct:.1f}% of those stopped trades "
        f"would have recovered to a positive 24-hour close. A 2% stop is hit {moderate.stop_hit_pct:.1f}% of the time, "
        f"and {moderate.stopped_then_24h_positive_pct:.1f}% of those trades would have recovered.",
        "",
        "The 4% stop is the leading fixed-stop candidate for the unfiltered reference setup. It improves mean return "
        "in both periods: +0.354% to +0.462% earlier and +0.319% to +0.385% later. It also changes the observed worst "
        "24-hour outcomes from -16.11% and -20.31% to -4.00%. The 5% stop also improves the reference mean in both "
        "periods, but protects less and has a lower full-history mean than 4%.",
        "",
        "Do not adopt a fixed stop as a final rule yet. The reference 4% block intervals include zero in both periods, "
        "only 30 of 81 configurations improve with 4% in the later period, and none of the 102 descriptive screen "
        "passes has a positive block interval in both periods. Stops at 0.5% through 2% are rejected for the reference "
        "setup because they reduce full-history mean return and trigger on 50% to 85% of entries. Every tested stop "
        "also reduces the full-history mean in the reference bullish-regime segment, so the 4% candidate applies only "
        "to the unfiltered reference sample and must be retested with exits and costs.",
        "",
        "This run stops after downside-protection analysis. No Step 5 exit or trailing optimization is performed.",
        "",
        "## Artifacts",
        "",
        "`protection_summary.csv` contains every setup, period, segment, and stop. `stability_screen.csv` and "
        "`cross_grid_effects.csv` contain robustness checks. Per-dataset Parquet files preserve episode-level stop "
        "outcomes. `validation.csv` and `SUCCESS.json` record audit completion. Run "
        "`python -B -m src.research.stage15_risk.run` to reproduce into a new output directory.",
        "",
    ]
    (path / "downside_protection_report.md").write_text("\n".join(report))
    make_figures(path, reference_all, cross)


def make_figures(path, reference, cross):
    os.environ.setdefault("MPLCONFIGDIR", str(path / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot = reference.copy()
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    axes[0].plot(plot.protection, plot.return_24h_mean_pct, marker="o", label="Mean")
    axes[0].plot(plot.protection, plot.return_24h_p10_pct, marker="o", label="10th percentile")
    axes[0].axhline(0, color="black", linewidth=0.7)
    axes[0].tick_params(axis="x", rotation=45)
    axes[0].set_ylabel("24h outcome (%)")
    axes[0].set_title("Reference return and downside")
    axes[0].legend()
    stopped = plot.loc[plot.protection.ne("no_stop")]
    axes[1].plot(stopped.protection, stopped.stop_hit_pct, marker="o", label="Stop hit")
    axes[1].plot(
        stopped.protection,
        stopped.stopped_then_24h_positive_pct,
        marker="o",
        label="Stopped then recovered positive",
    )
    axes[1].tick_params(axis="x", rotation=45)
    axes[1].set_ylabel("Share (%)")
    axes[1].set_title("Reference protection tradeoff")
    axes[1].legend()
    figure.savefig(path / "reference_downside_protection.png", dpi=140)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(9, 5), layout="constrained")
    axis.bar(cross.protection, cross.configs_mean_improved, color="#376d91")
    axis.axhline(40.5, color="#b5554d", linestyle="--", linewidth=1)
    axis.tick_params(axis="x", rotation=45)
    axis.set_ylabel("Configurations with higher mean (of 81)")
    axis.set_title("Later-period stop consistency across the grid")
    figure.savefig(path / "cross_grid_stop_consistency.png", dpi=140)
    plt.close(figure)
