"""Report and chart for realistic spot execution."""

import numpy as np
import pandas as pd


def markdown(frame):
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = ["—" if isinstance(v, (float, np.floating)) and pd.isna(v)
                 else f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v) for v in values]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def write_report(path, summary, protected_count, audit_rows):
    rows = []
    for timeframe, market_filter in [("5m", "all_market_conditions"), ("3m", "avoid_strong_bearish")]:
        selected = summary.loc[summary.timeframe.eq(timeframe) & summary.average_type.eq("15d")
                               & summary.touch_zone.eq(.5) & summary.market_filter.eq(market_filter)].copy()
        selected["setup"] = f"{timeframe} / {market_filter}"
        rows.append(selected)
    reference = pd.concat(rows)
    order = {name: index for index, name in enumerate(["gross", "fee_only", "realistic", "stressed", "severe"])}
    reference["sort"] = reference.scenario.map(order); reference = reference.sort_values(["setup", "sort"])
    columns = ["setup", "scenario", "nonoverlap_trades_earlier", "nonoverlap_trades_later",
               "mean_return_pct_earlier", "mean_return_pct_later", "median_return_pct_earlier",
               "median_return_pct_later", "execution_drag_earlier_pp", "execution_drag_later_pp",
               "positive_quarters_pct", "ci95_low_earlier", "ci95_low_later", "execution_pass", "robust_pass"]
    realistic = summary.loc[summary.scenario.eq("realistic")]
    text = f"""# Stage 1.5 v2 — Realistic Spot Execution Analysis

## Purpose and assumptions

This step replays long-only spot orders with one open position per configuration. Targets and stops are measured from the actual entry fill. Both entry and exit pay the stated fee and adverse slippage. Same-minute target/stop conflicts use the stop, stops gap adversely, and the maximum hold remains 24 hours.

The realistic assumption is 10 basis points fee plus 2 basis points slippage on each side. Stress cases increase slippage to 5 and 10 basis points per side. These are research assumptions, not a live exchange fee quote.

## Reference results

{markdown(reference[columns])}

## Robustness result

- Execution comparisons: {len(summary):,} (27 configurations x 2 market variants x 5 scenarios).
- Realistic scenarios positive in both periods: {int((realistic.mean_return_pct_earlier.gt(0) & realistic.mean_return_pct_later.gt(0)).sum()):,}.
- Realistic execution-screen passes: {int(realistic.execution_pass.sum()):,}.
- Realistic robust passes with positive block confidence bounds: {int(realistic.robust_pass.sum()):,}.
- Audited reference event rows: {audit_rows:,}.
- Protected earlier files verified unchanged: {protected_count:,}.

All results are spot-only. The historical later period is not untouched Stage 2 evidence.
"""
    (path / "realistic_execution_report.md").write_text(text)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pivot = reference.pivot(index="scenario", columns="setup", values=["mean_return_pct_earlier", "mean_return_pct_later"])
    pivot = pivot.reindex(["gross", "fee_only", "realistic", "stressed", "severe"])
    ax = pivot.plot(kind="bar", figsize=(12, 6))
    ax.axhline(0, color="black", linewidth=.8); ax.set_ylabel("Mean spot return (%)")
    ax.set_title("Execution-cost sensitivity"); ax.tick_params(axis="x", rotation=0)
    ax.figure.tight_layout(); ax.figure.savefig(path / "execution_cost_sensitivity.png", dpi=160)
    plt.close(ax.figure)

