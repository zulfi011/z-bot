"""Create Step 5 report and figures."""

import os
import numpy as np
import pandas as pd


def table(frame):
    lines = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = ["—" if pd.isna(v) else (f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v)) for v in values]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(path, summary, screen, cross, protected_count, candidate_rows):
    reference = summary.loc[
        summary.asset.eq("SOLUSDT") & summary.timeframe.eq("5m")
        & summary.average_type.eq("15d") & summary.touch_zone.eq(.5)
        & summary.policy.eq("first_touch_0m") & summary.segment.eq("all_entries")
    ]
    cols = ["period", "strategy", "return_mean_pct", "return_median_pct",
            "expected_shortfall_10_pct", "mean_change_vs_hold_pp", "tail_change_vs_hold_pp",
            "median_duration_minutes", "profit_target_exit_pct", "trailing_stop_exit_pct",
            "protective_stop_exit_pct"]
    ref_all = reference.loc[reference.period.eq("all")]
    time_rows = reference.loc[reference.exit_family.eq("fixed_time")].sort_values(["period", "maximum_hold_minutes", "risk_variant"])
    target_rows = reference.loc[reference.exit_family.eq("profit_target") & reference.target_pct.isin([1, 2, 2.5, 3, 4, 5])].sort_values(["period", "target_pct", "risk_variant"])
    trail_rows = reference.loc[reference.exit_family.eq("trailing")].sort_values(["period", "trail_giveback_pct", "risk_variant"])
    stable = screen.loc[screen.stability_screen]
    stable_cols = ["asset", "timeframe", "average_type", "touch_zone", "policy", "segment",
                   "strategy", "entries_earlier", "entries_later", "return_mean_pct_earlier",
                   "return_mean_pct_later", "mean_change_vs_hold_pp_earlier",
                   "mean_change_vs_hold_pp_later", "tail_change_vs_hold_pp_later", "positive_block_ci_both"]
    cross_later = cross.loc[
        cross.policy.eq("first_touch_0m") & cross.segment.eq("all_entries")
        & cross.period.eq("later") & cross.strategy.ne("time_1440_no_stop")
    ].sort_values(["configs_mean_improved", "median_mean_change_vs_hold_pp"], ascending=False)
    cross_cols = ["strategy", "exit_family", "configurations", "configs_positive_mean",
                  "configs_mean_improved", "configs_tail_improved", "median_mean_change_vs_hold_pp",
                  "median_tail_change_vs_hold_pp", "median_duration_minutes"]
    report = [
        "# Stage 1.5 Step 5 — Exit and Holding Time", "",
        "## Frozen scope and execution", "",
        "This step keeps the deduplicated episodes, first-touch and 30-minute bullish-candle entries, and Step 3 market context unchanged across all 81 configurations. It compares eight fixed holding periods, seven profit targets with a 24-hour cap, and four trailing exits activated at +2.5%. Every exit is tested without a stop and with the Step 4 4% stop candidate.", "",
        "Time exits use the close of the final raw minute. Profit targets fill at the better of the target or a gap-up minute open. The 4% stop fills at the worse of its threshold or a gap-down minute open. A target and stop reached in the same minute use the stop result and remain marked ambiguous. Trailing begins only after the +2.5% activation minute closes and uses the peak from completed minutes, preventing intraminute high/low ordering from creating optimistic exits.", "",
        "All returns are gross single-opportunity outcomes. Fees, slippage beyond gap handling, position overlap, sizing, and portfolio capital are not modeled.", "",
        "## Reference fixed holding periods", "", table(time_rows[cols]), "",
        "## Reference profit-target exits", "", table(target_rows[cols]), "",
        "## Reference +2.5%-activated trailing exits", "", table(trail_rows[cols]), "",
        "The comparison baseline is holding without a stop for 1,440 minutes. Expected shortfall is the mean of the worst 10% of outcomes. Positive tail change means the exit reduced those losses relative to the baseline.", "",
        "## Cross-grid later-period evidence", "", table(cross_later[cross_cols].head(20)), "",
        "Configurations share episodes and price paths, so the grid count is a consistency check rather than 81 independent experiments.", "",
        "## Stability screen", "",
        f"{len(stable)} combinations pass the descriptive screen: at least 100 entries per period, positive mean and median in both periods, and improvement over the 24-hour hold in both mean and worst-decile outcome in both periods. The leading 15 by later-period mean improvement are shown.", "",
        table(stable[stable_cols].head(15)), "",
        f"{int(screen.positive_block_ci_both.sum())} screened combinations also have a positive exploratory seven-day block interval in both periods. Intervals are not adjusted for the many exit choices and do not establish an independent trading edge.", "",
        "## Validation and preservation", "",
        f"The run evaluates {candidate_rows:,} inherited episode-entry rows. Direct scalar replays independently verify fixed-time endpoints, target and stop ordering, gap fills, trailing activation, prior-peak trails, duration, and incomplete-window handling. Candidate identity, entry price, 24-hour baseline, nested time completeness, output round trips, and summary cardinality are also checked.", "",
        f"Before/after SHA-256 confirms {protected_count} prior files are unchanged. All outputs are isolated under Step 5 paths.", "",
        "## Step 5 decision", "",
        "For SOL / 15D / 5m / ±0.5%, retain the 24-hour hold as the primary exit. No alternative passes the stability screen for this reference setup. Shorter fixed holds sharply reduce mean return. A +4% target with the 4% stop is strong later (+0.561% mean versus +0.319% holding) but weak earlier (+0.241% versus +0.354%). The 50% giveback trail without a stop shows the reverse: it improves earlier (+0.407% versus +0.354%) but falls behind later (+0.264% versus +0.319%). These reversals reject both as reference exit rules for now.", "",
        "Keep the 4% stop with the 24-hour hold as a risk-control variant, not the primary exit: it raises reference mean in both periods and limits the worst observed outcomes, but its earlier median is slightly negative. In the bullish reference segment, the unchanged 24-hour hold without a stop remains strongest overall.", "",
        "Other configurations are not discarded. ETH / 15D / ±0.5% with a +2.5%-activated 50% giveback trail and 4% stop passes the descriptive screen on 1m, 3m, and 5m data. On ETH 5m, mean return is +0.500% earlier and +0.310% later, versus +0.408% and +0.086% for holding. SOL / 15D / 5m / ±1.0% with the same exit also passes. Carry these as secondary candidates into final robustness testing.", "",
        "Across the full study, 99 combinations pass the descriptive screen but none has a positive block interval in both periods. Therefore no refined exit is final, and the secondary candidates require dependence, cost, and sensitivity checks before Stage 2.", "",
        "This run stops after exit and holding-time analysis. No final strategy selection or Stage 2 implementation is performed.", "",
        "## Artifacts", "",
        "`exit_summary.csv` contains all strategies, periods, and segments. `stability_screen.csv` and `cross_grid_effects.csv` contain robustness checks. Per-dataset Parquet files retain episode-level outcomes. `validation.csv` and `SUCCESS.json` record audit completion. Run `python -B -m src.research.stage15_exit.run` to reproduce into a new directory.", "",
    ]
    (path / "exit_holding_report.md").write_text("\n".join(report))
    make_figures(path, ref_all, cross_later)


def make_figures(path, reference, cross):
    os.environ.setdefault("MPLCONFIGDIR", str(path / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    time = reference.loc[reference.exit_family.eq("fixed_time")]
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for risk, group in time.groupby("risk_variant"):
        group = group.sort_values("maximum_hold_minutes")
        axes[0].plot(group.maximum_hold_minutes / 60, group.return_mean_pct, marker="o", label=risk)
        axes[1].plot(group.maximum_hold_minutes / 60, group.expected_shortfall_10_pct, marker="o", label=risk)
    axes[0].set_title("Reference mean return by holding time")
    axes[1].set_title("Reference worst-decile mean by holding time")
    for axis in axes:
        axis.set_xlabel("Maximum holding time (hours)"); axis.set_ylabel("Return (%)"); axis.legend()
    figure.savefig(path / "reference_holding_times.png", dpi=140); plt.close(figure)
    top = cross.head(15).sort_values("configs_mean_improved")
    figure, axis = plt.subplots(figsize=(10, 7), layout="constrained")
    axis.barh(top.strategy, top.configs_mean_improved, color="#376d91")
    axis.axvline(40.5, color="#b5554d", linestyle="--", linewidth=1)
    axis.set_xlabel("Configurations improving mean return (of 81)")
    axis.set_title("Later-period exit consistency")
    figure.savefig(path / "cross_grid_exit_consistency.png", dpi=140); plt.close(figure)
