"""Readable report and chart for Stage 1.5 v2 market filters."""

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


def write_report(path, summary, threshold, training_origins, protected_count, event_rows):
    main = summary.loc[
        summary.asset.eq("SOLUSDT") & summary.timeframe.eq("5m")
        & summary.average_type.eq("15d") & summary.touch_zone.eq(.5)
    ].copy()
    order = ["all_market_conditions", "rising_15d", "sol_and_btc_rising_15d",
             "avoid_strong_bearish", "avoid_extreme_volatility", "avoid_bearish_and_extreme",
             "rising_15d_and_safe", "all_filters"]
    main["sort"] = main.filter_variant.map({value: index for index, value in enumerate(order)})
    main = main.sort_values("sort")
    columns = ["filter_variant", "entries_earlier", "entries_later",
               "nonoverlap_trades_earlier", "nonoverlap_trades_later",
               "retention_pct_earlier", "retention_pct_later",
               "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later",
               "target_pct_earlier", "target_pct_later", "stop_pct_earlier", "stop_pct_later",
               "positive_quarters_pct", "net_ci95_low_earlier", "net_ci95_low_later",
               "provisional_pass", "robust_pass"]
    enough = summary.loc[summary.enough_samples]
    text = f"""# Stage 1.5 v2 — Market Filter Analysis

## Purpose and fixed definitions

This step tests whether causal market context can remove weak SOL entries from the current candidate. The entry remains bullish-candle confirmation within 30 minutes after a deduplicated touch from below. The exit remains +4% target, -4% stop, and a 24-hour maximum hold.

The 15-day trend compares the average known at the signal with the value known 24 hours earlier. Joint trend requires both SOL and BTC to rise. Strongly bearish means 7-day < 15-day < 30-day averages. Extreme volatility means the previous 24-hour range exceeded the earlier-period 90th-percentile threshold of {threshold:.4f}% fitted from {training_origins:,} unique signal times.

## Reference SOL setup

{markdown(main[columns])}

## Robustness result

- SOL configurations evaluated: 27 across 8 predefined filter variants ({len(summary):,} comparisons).
- Comparisons retaining the required samples: {int(summary.enough_samples.sum()):,}.
- Sample-qualified comparisons profitable after costs in both periods: {int((enough.cost_survives_both).sum()):,}.
- Provisional passes that also improved the unfiltered baseline in both periods: {int(summary.provisional_pass.sum()):,}.
- Robust passes with positive 95% block confidence bounds in both periods: {int(summary.robust_pass.sum()):,}.
- Audited reference event rows: {event_rows:,}.
- Protected earlier files verified unchanged: {protected_count:,}.

The later period was used in earlier research and is not untouched out-of-sample evidence.
"""
    (path / "market_filter_report.md").write_text(text)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = np.arange(len(main)); width = .36
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(x - width / 2, main.net_0_2_mean_pct_earlier, width, label="Earlier")
    ax.bar(x + width / 2, main.net_0_2_mean_pct_later, width, label="Later")
    ax.axhline(0, color="black", linewidth=.8)
    labels = [value.replace("_", "\n") for value in main.filter_variant]
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("Mean return after 0.2% cost (%)")
    ax.set_title("SOL 15D / 5m / ±0.5% market filters")
    ax.legend(); fig.tight_layout()
    fig.savefig(path / "reference_market_filter_comparison.png", dpi=160)
    plt.close(fig)

