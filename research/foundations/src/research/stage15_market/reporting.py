"""Step 3 report and compact static figures."""

import os
import numpy as np
import pandas as pd


def table(frame):
    lines = ["| " + " | ".join(frame.columns) + " |",
             "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            cells.append(
                "—" if pd.isna(value) else
                (f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value))
            )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(path, summary, screen, effects, thresholds, protected_count):
    primary = summary.loc[
        summary.asset.eq("SOLUSDT") & summary.timeframe.eq("5m")
        & summary.average_type.eq("15d") & summary.touch_zone.eq(.5)
        & summary.rule.eq("first_touch") & summary.period.eq("all")
    ]
    columns = ["condition", "value", "entries", "return_24h_mean_pct",
               "return_24h_median_pct", "mae_24h_median_pct", "mfe_mae_ratio",
               "target_first_2_5_decisive_pct", "mean_advantage_vs_complement_pp"]
    primary_focus = primary.loc[
        primary.condition.isin(["origin_regime", "approach", "average_slope_24h",
                                "prior_return_sign", "prior_range_band", "touch_close_side"])
        & ~primary.value.isin(["missing", "unknown"]), columns
    ].sort_values(["condition", "value"])
    stable = screen.loc[screen.stability_screen]
    stable_columns = ["asset", "timeframe", "average_type", "touch_zone", "rule",
                      "condition", "value", "entries_earlier", "entries_later",
                      "return_24h_mean_pct_earlier", "return_24h_mean_pct_later",
                      "return_24h_median_pct_later", "mae_24h_median_pct_later",
                      "mean_advantage_vs_complement_pp_later", "positive_block_ci_both"]
    cross = effects.loc[
        effects.period.eq("later") & effects.rule.eq("first_touch")
        & effects.condition.ne("regime_approach")
        & ~effects.value.isin(["missing", "unknown"])
    ].sort_values(["condition", "value"])
    cross_columns = ["condition", "value", "configurations", "median_entry_share_pct",
                     "configs_positive_mean", "configs_mean_beats_complement",
                     "median_mean_advantage_vs_complement_pp", "median_mfe_mae_ratio"]

    report = [
        "# Stage 1.5 Step 3 — Market Conditions", "",
        "## Scope and causal definitions", "",
        "This step reassesses conditions at the end of the first-touch candle across all 81 configurations. "
        "It carries forward the primary first-touch entry and the secondary 30-minute bullish-candle entry. "
        "It does not modify entry execution, stops, exits, position state, or costs.", "",
        "Conditions are: completed-day average regime; approach from above/below the zone; 24h average slope; "
        "sign of the prior 24h return; prior 24h high-low range band; and whether the touch candle closes above "
        "the average. Regime-plus-approach is the only interaction searched. Context uses data known by the "
        "first-touch decision boundary. No future episode or outcome data enters a condition.", "",
        "Low/medium/high prior-range thresholds are asset-specific terciles fitted on unique earlier-period origin "
        "timestamps and frozen before the later-period evaluation. This prevents later outcomes from defining bands.", "",
        "## Volatility thresholds", "", table(thresholds), "",
        "## Reference setup: SOL / 15D / 5m / ±0.5%, first-touch entry", "",
        table(primary_focus), "",
        "The advantage column compares a condition with all other values of the same condition. It describes "
        "selection, not the benefit of delaying entry. A positive value means the selected condition had a larger "
        "mean 24h return than its complement.", "",
        "## Cross-grid later-period evidence: first-touch entry", "",
        table(cross[cross_columns]), "",
        "Cross-grid counts are descriptive and share market observations across configurations.", "",
        "## Stability screen across every configuration", "",
        f"{len(stable)} setup-entry-condition combinations pass the prespecified descriptive screen: at least 100 "
        "entries in both periods, positive mean and median return in both, MFE/MAE above one in both, and mean return "
        "above the condition's complement in both. The first 15 by later-period complement advantage are shown.", "",
        table(stable[stable_columns].head(15)), "",
        "`positive_block_ci_both` means the exploratory seven-day block interval for selected-versus-complement mean "
        "return is above zero in both periods. It is not adjusted for the many hypotheses tested. This screen finds "
        "hypotheses; it does not establish optimal filters. Results share episodes across nested zones, "
        "averages, and timeframes, and the later period was already visible during Stage 1.", "",
        "## Validation and preservation", "",
        "Every retained Step 2 outcome is copied exactly. Context timestamps, raw 24h history, average slope, and touch "
        "close distance are independently replayed on deterministic samples. Volatility thresholds are recomputed from "
        "earlier unique origins, candidate cardinality is checked, incomplete histories stay missing, and Parquet/CSV "
        "round trips are verified.", "",
        f"Before/after SHA-256 confirms {protected_count} protected Stage 1, Step 1, and Step 2 files are unchanged. "
        "All new files are isolated under Step 3 paths.", "",
        "## Step 3 decision", "",
        "Do not adopt a hard market filter yet. For the reference setup, bullish regime is the leading broad condition: "
        "mean/median 24h return was +1.206%/+0.775% earlier and +0.563%/+0.746% later. Approaching from below and a "
        "rising 15D average are useful secondary condition candidates, but approach from below carries somewhat deeper "
        "MAE and is not consistently superior across all configurations. Combining bullish regime with approach from "
        "below leaves only 49 later-period reference entries and does not remain stable, so do not combine them into a rule.", "",
        "Bearish regime is rejected as a preferred condition for this setup because its earlier mean/median return was "
        "-2.082%/-2.849%, despite improving later. Prior-return sign and volatility band reversed between periods and "
        "should not be used as filters. None of the 151 descriptive hypotheses had an exploratory positive block interval "
        "in both periods, so the evidence supports carrying candidates forward for controlled testing rather than "
        "declaring a market-condition edge. Missing-regime observations are retained for audit only.", "",
        "This run stops after market-condition analysis. No stop, exit, or Stage 2 work is performed.", "",
        "## Artifacts", "",
        "`condition_summary.csv` contains all periods and condition groups. `stability_screen.csv` contains every screen "
        "result. `cross_grid_effects.csv` summarizes consistency across configurations. `market_context.csv` and the "
        "per-dataset Parquet files preserve episode-level context and outcomes. `validation.csv` and `SUCCESS.json` "
        "record completion. Run `python -B -m src.research.stage15_market.run` to reproduce into a new output directory.", "",
    ]
    (path / "market_conditions_report.md").write_text("\n".join(report))
    make_figures(path, primary_focus, stable)


def make_figures(path, primary, stable):
    os.environ.setdefault("MPLCONFIGDIR", str(path / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot = primary.copy()
    plot["label"] = plot.condition.str.replace("_", " ") + ": " + plot.value
    plot = plot.sort_values("return_24h_mean_pct")
    figure, axis = plt.subplots(figsize=(10, 8), layout="constrained")
    colors = np.where(plot.return_24h_mean_pct >= 0, "#24745d", "#b5554d")
    axis.barh(plot.label, plot.return_24h_mean_pct, color=colors)
    axis.axvline(0, color="black", linewidth=.7)
    axis.set_xlabel("Mean 24h return from first-touch entry (%)")
    axis.set_title("Reference setup by causal market condition")
    figure.savefig(path / "reference_market_conditions.png", dpi=140)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(9, 6), layout="constrained")
    counts = stable.groupby(["condition", "value"]).size().sort_values()
    counts.plot.barh(ax=axis, color="#376d91")
    axis.set_xlabel("Setup-entry combinations passing stability screen")
    axis.set_ylabel("")
    axis.set_title("Stable condition hypotheses across the full grid")
    figure.savefig(path / "stable_condition_counts.png", dpi=140)
    plt.close(figure)
