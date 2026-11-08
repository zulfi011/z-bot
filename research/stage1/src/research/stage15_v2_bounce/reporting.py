"""Tables, chart, and readable report for confirmed-bounce research."""

import numpy as np
import pandas as pd


def markdown(frame):
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            if isinstance(value, (float, np.floating)):
                cells.append("—" if pd.isna(value) else f"{value:.4f}")
            else:
                cells.append(str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def write_report(path, summary, baseline, protected_count, candidate_rows):
    main = summary.loc[
        summary.asset.eq("SOLUSDT") & summary.timeframe.eq("5m")
        & summary.average_type.eq("15d") & summary.touch_zone.eq(.5)
    ].copy()
    cols = ["policy", "confirmed_entries_earlier", "confirmed_entries_later",
            "nonoverlap_trades_earlier", "nonoverlap_trades_later",
            "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later",
            "target_pct_earlier", "target_pct_later", "stop_pct_earlier", "stop_pct_later",
            "positive_quarters_pct", "net_ci95_low_earlier", "net_ci95_low_later",
            "provisional_pass", "robust_pass"]
    base_main = baseline.loc[
        baseline.asset.eq("SOLUSDT") & baseline.timeframe.eq("5m")
        & baseline.average_type.eq("15d") & baseline.touch_zone.eq(.5)
    ][["entry_method", "nonoverlap_trades_earlier", "nonoverlap_trades_later",
       "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later",
       "target_pct_earlier", "target_pct_later", "stop_pct_earlier", "stop_pct_later",
       "positive_quarters_pct"]]
    text = f"""# Stage 1.5 v2 — Confirmed Bounce Entry Analysis

## Purpose and rule

This step tests whether waiting for visible buyer confirmation improves entries after a deduplicated moving-average touch from below. A valid setup must reclaim the average within 30 minutes. A later candle must remain above the average and trade strictly above the reclaim candle's high. Execution occurs at the next source-candle boundary, priced at the corresponding raw 1-minute open. The immediate policy permits only the next candle; the other policies permit 15 or 30 minutes. A close at or below the average before breakout cancels the setup.

All policies use the frozen +4% target, -4% stop, 24-hour maximum hold, conservative same-minute stop priority, one position at a time, and 0.2% round-trip cost.

## Reference setup

{markdown(main[cols])}

## Comparison with the current candidate

{markdown(base_main)}

## Cross-grid robustness

- Configurations evaluated: {len(summary):,} (81 configurations x 3 bounce windows).
- Provisional passes: {int(summary.provisional_pass.sum()):,}.
- Robust passes with positive 95% block confidence bounds in both periods: {int(summary.robust_pass.sum()):,}.
- Candidate rows audited: {candidate_rows:,}.
- Protected pre-existing files verified unchanged: {protected_count:,}.

The later period has already been inspected during Stage 1.5 and is not untouched out-of-sample evidence. Any surviving rule still requires official Stage 2 forward validation.
"""
    (path / "bounce_entry_report.md").write_text(text)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    order = ["bounce_break_immediate", "bounce_break_15m", "bounce_break_30m"]
    plot = main.set_index("policy").reindex(order)
    x = np.arange(len(plot)); width = .35
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width / 2, plot.net_0_2_mean_pct_earlier, width, label="Earlier")
    ax.bar(x + width / 2, plot.net_0_2_mean_pct_later, width, label="Later")
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xticks(x, ["Immediate", "15 minutes", "30 minutes"])
    ax.set_ylabel("Mean return after 0.2% cost (%)")
    ax.set_title("SOL 15D / 5m / ±0.5% confirmed-bounce entries")
    ax.legend(); fig.tight_layout()
    fig.savefig(path / "reference_bounce_comparison.png", dpi=160)
    plt.close(fig)
