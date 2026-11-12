"""Report and chart for volatility-adjusted spot exits."""

import numpy as np
import pandas as pd


def markdown(frame):
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = []
        for value in values:
            cells.append("—" if isinstance(value, (float, np.floating)) and pd.isna(value)
                         else f"{value:.4f}" if isinstance(value, (float, np.floating)) else str(value))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def write_report(path, summary, atr_stats, protected_count, audit_rows):
    main_5m = summary.loc[
        summary.timeframe.eq("5m") & summary.average_type.eq("15d") & summary.touch_zone.eq(.5)
        & summary.market_filter.eq("all_market_conditions")
    ].sort_values("worst_period_net_mean_pct", ascending=False)
    market_3m = summary.loc[
        summary.timeframe.eq("3m") & summary.average_type.eq("15d") & summary.touch_zone.eq(.5)
        & summary.market_filter.eq("avoid_strong_bearish")
    ].sort_values("worst_period_net_mean_pct", ascending=False)
    columns = ["strategy", "nonoverlap_trades_earlier", "nonoverlap_trades_later",
               "median_stop_distance_pct_earlier", "median_target_distance_pct_earlier",
               "net_0_2_mean_pct_earlier", "net_0_2_mean_pct_later",
               "net_0_2_median_pct_earlier", "net_0_2_median_pct_later",
               "positive_quarters_pct", "net_ci95_low_earlier", "net_ci95_low_later",
               "provisional_pass", "robust_pass"]
    provisional = summary.loc[summary.provisional_pass, ["timeframe", "average_type", "touch_zone",
                                                          "market_filter", *columns]]
    text = f"""# Stage 1.5 v2 — ATR Spot Exit Analysis

## Purpose and execution model

This analysis replaces fixed percentages with volatility-adjusted exits for long-only SOL spot purchases. It uses the last completed one-hour candle's 14-period Wilder ATR. Stops are 1.5x, 2x, or 2.5x ATR from entry; targets are 1.5R, 2R, or 2.5R. Every trade has a 24-hour maximum hold, conservative same-minute stop priority, one open position per configuration, and 0.2% round-trip cost. There are no shorts, leverage, liquidation, or futures funding.

Median ATR at studied entries was {atr_stats['median_atr_pct']:.4f}% of spot price (10th–90th percentile: {atr_stats['p10_atr_pct']:.4f}%–{atr_stats['p90_atr_pct']:.4f}%).

## Current 5-minute reference setup

{markdown(main_5m[columns])}

## Previous step's 3-minute bearish-filter setup

{markdown(market_3m[columns])}

## Provisional ATR candidates

{markdown(provisional) if len(provisional) else 'No ATR strategy passed the provisional screen.'}

## Robustness result

- Comparisons evaluated: {len(summary):,} (27 SOL configurations x 2 market variants x 10 exits).
- Provisional ATR passes: {int(summary.provisional_pass.sum()):,}.
- Robust ATR passes with positive block confidence bounds in both periods: {int(summary.robust_pass.sum()):,}.
- Reference event rows audited: {audit_rows:,}.
- Protected earlier files verified unchanged: {protected_count:,}.

These are historical spot results. The later period has already been inspected and is not untouched Stage 2 evidence.
"""
    (path / "atr_exit_report.md").write_text(text)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plot = main_5m.head(10)
    x = np.arange(len(plot)); width = .36
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.bar(x - width / 2, plot.net_0_2_mean_pct_earlier, width, label="Earlier")
    ax.bar(x + width / 2, plot.net_0_2_mean_pct_later, width, label="Later")
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xticks(x, plot.strategy.str.replace("atr_stop_", "S").str.replace("_rr_", " R").str.replace("_", "."),
                  rotation=35, ha="right")
    ax.set_ylabel("Mean spot return after 0.2% cost (%)")
    ax.set_title("SOL 15D / 5m / ±0.5% ATR exit comparison")
    ax.legend(); fig.tight_layout()
    fig.savefig(path / "reference_atr_exit_comparison.png", dpi=160)
    plt.close(fig)

