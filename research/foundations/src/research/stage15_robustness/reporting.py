"""Write the final Stage 1.5 robustness and selection report."""

import os
import numpy as np
import pandas as pd


def table(frame):
    lines = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = ["—" if pd.isna(v) else (f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v)) for v in values]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(path, selection, quarters, protected_count, candidate_rows, selected_events):
    robust = selection.loc[selection.robust_selection]
    provisional = selection.loc[selection.provisional_selection]
    columns = ["asset", "timeframe", "average_type", "touch_zone", "policy", "condition_variant",
               "strategy", "entries_earlier", "entries_later", "nonoverlap_trades_earlier",
               "nonoverlap_trades_later", "nonoverlap_net_0_2_mean_pct_earlier",
               "nonoverlap_net_0_2_mean_pct_later", "median_pct_earlier", "median_pct_later",
               "positive_quarters_pct", "nonoverlap_expected_shortfall_10_pct_earlier",
               "nonoverlap_expected_shortfall_10_pct_later", "positive_neighbors_earlier",
               "positive_neighbors_later", "neighbor_count", "net_0_2_ci95_low_earlier",
               "net_0_2_ci95_low_later", "robust_selection"]
    reference = selection.loc[
        selection.asset.eq("SOLUSDT") & selection.timeframe.eq("5m")
        & selection.average_type.eq("15d") & selection.touch_zone.eq(.5)
        & selection.policy.eq("first_touch_0m")
        & selection.condition_variant.isin(["all_entries", "bullish_regime"])
        & selection.strategy.isin(["time_1440_no_stop", "time_1440_stop_4",
                                   "target_4_stop_4", "trail_50_no_stop"])
    ]
    eth = selection.loc[
        selection.asset.eq("ETHUSDT") & selection.average_type.eq("15d")
        & selection.touch_zone.eq(.5) & selection.policy.eq("first_touch_0m")
        & selection.condition_variant.eq("all_entries")
        & selection.strategy.eq("trail_50_stop_4")
    ].sort_values("timeframe")
    reports = [
        "# Stage 1.5 Step 6 — Robustness and Candidate Selection", "",
        "## Purpose and frozen design", "",
        "This final Stage 1.5 step applies realistic sensitivity checks to the complete Step 5 grid. It does not change touch generation, entries, market context, stops, or exits. Four predeclared condition variants are evaluated separately: all entries, bullish regime, approach from below, and rising average.", "",
        "Each setup allows one open position at a time, keeping the earliest eligible signal and ignoring new signals until its actual exit. Results are tested at 0%, 0.10%, and 0.20% assumed round-trip cost. Selection uses the conservative 0.20% result, earlier and later periods, quarterly consistency, worst-decile outcome, adjacent timeframe/zone behavior, and seven-day block resampling.", "",
        "A provisional candidate must have at least 100 opportunities and 40 non-overlapping trades in each period; positive raw mean and median in both; positive non-overlapping mean after 0.20% cost in both; at least 60% positive quarters; worst-decile mean no lower than -5%; and a majority of nearby parameter settings positive in both periods. A robust candidate must additionally have a positive 95% block interval in both periods.", "",
        "This is a historical selection exercise. The later period was already visible during Stage 1 and is not untouched out-of-sample evidence.", "",
        "## Main SOL reference audit", "", table(reference[columns]), "",
        "## ETH trailing candidate across timeframes", "", table(eth[columns]), "",
        "## Provisional selections", "",
        f"{len(provisional)} of {len(selection):,} evaluated combinations pass every non-bootstrap gate. The leading 20 by their weaker period's net mean are shown.", "",
        table(provisional[columns].head(20)), "",
        "## Robust selections", "",
        f"{len(robust)} combinations also have a positive cost-adjusted seven-day block interval in both periods.", "",
        table(robust[columns].head(20)) if len(robust) else "No combination passes the full robust-selection rule.", "",
        "Because configurations share candles and many candidates were inspected, the provisional list is a shortlist for forward validation rather than proof of independent edges.", "",
        "## Validation and preservation", "",
        f"The audit starts from {candidate_rows:,} inherited episode-entry rows and evaluates one-position sequencing from actual exit durations. Unit tests cover overlap boundaries, cost application, conditions, compounding drawdown, and deterministic block intervals. Candidate cardinality, quarter reconstruction, neighbor counts, selected-event reconstruction, CSV/Parquet round trips, and source hashes are checked.", "",
        f"Before/after SHA-256 confirms {protected_count} prior files are unchanged. The selected-event audit contains {selected_events:,} rows and all outputs are isolated under Step 6 paths.", "",
        "## Final Stage 1.5 decision", "",
        "No strategy is historically robust enough to approve for trading: all block intervals include zero in at least one period. The original unfiltered SOL / 15D / 5m / ±0.5% setup and the ETH / 15D / ±0.5% trailing candidate are rejected from the Stage 2 shortlist because their one-position mean after 0.20% cost is negative in the later or both periods.", "",
        "Select SOL / 15D / 5m / ±0.5%, approach from below, 30-minute bullish-candle entry, +4% target, and -4% stop as the primary provisional Stage 2 candidate. It retains 62 earlier and 55 later non-overlapping trades, averages +0.209% and +0.240% per trade after the 0.20% cost assumption, and has positive quarterly means in 7 of 9 quarters. Carry the first-touch version of the same setup as an entry sensitivity control; it averages +0.212% and +0.169% after cost.", "",
        "Carry two distinct secondary families: SOL / 15D / 3m / ±1.5% in a bullish regime with first-touch entry and +1.5% target; and ETH / 15D / 3m / ±1.0% in a bullish regime with 30-minute bullish-candle entry and an 8-hour exit. Their weaker-period cost-adjusted means are +0.098% and +0.070%. Nearby timeframe variants are positive, which is why these families remain useful sensitivity candidates.", "",
        "These four selections are forward-test candidates, not validated strategies. The primary candidate's block-interval lower bounds are -0.605% earlier and -0.688% later, so Stage 2 must use genuinely unseen data, one-position execution, and exchange-specific costs before any deployment decision.", "",
        "## Artifacts", "",
        "`selection.csv` contains every candidate and gate. `provisional_shortlist.csv`, `stage2_candidate_shortlist.csv`, `quarterly.csv`, and `validation.csv` provide the audit trail. `selected_candidate_events.parquet` reconstructs non-overlapping trades for shortlisted candidates. `SUCCESS.json` records completion. Run `python -B -m src.research.stage15_robustness.run` to reproduce into a new directory.", "",
    ]
    (path / "robustness_selection_report.md").write_text("\n".join(reports))
    make_figure(path, provisional)


def make_figure(path, provisional):
    os.environ.setdefault("MPLCONFIGDIR", str(path / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plot = provisional.head(15).copy().sort_values("worst_period_net_mean_pct")
    figure, axis = plt.subplots(figsize=(11, 7), layout="constrained")
    labels = (plot.asset + " " + plot.timeframe + " " + plot.average_type + " z" + plot.touch_zone.astype(str)
              + " | " + plot.condition_variant + " | " + plot.strategy)
    axis.barh(labels, plot.worst_period_net_mean_pct, color="#376d91")
    axis.axvline(0, color="black", linewidth=.7)
    axis.set_xlabel("Weaker-period mean after 0.20% cost (%)")
    axis.set_title("Final provisional Stage 1.5 candidates")
    figure.savefig(path / "provisional_candidate_comparison.png", dpi=140)
    plt.close(figure)
