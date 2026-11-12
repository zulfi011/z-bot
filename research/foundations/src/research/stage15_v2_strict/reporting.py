"""Final robustness report and compact comparison chart."""

import numpy as np
import pandas as pd


def markdown(frame):
    rows = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for values in frame.itertuples(index=False, name=None):
        cells = ["—" if isinstance(v, (float, np.floating)) and pd.isna(v)
                 else f"{v:.4f}" if isinstance(v, (float, np.floating)) else str(v) for v in values]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def write_report(path, summary, quarters, neighbors, protected_count):
    columns = ["candidate", "nonoverlap_trades_earlier", "nonoverlap_trades_later",
               "mean_pct_earlier", "mean_pct_later", "median_pct_earlier", "median_pct_later",
               "positive_quarters_pct", "worst_quarter_mean_pct", "worst_trade_pct_earlier",
               "worst_trade_pct_later", "expected_shortfall_10_pct_earlier",
               "expected_shortfall_10_pct_later", "max_drawdown_pct_earlier",
               "max_drawdown_pct_later", "positive_neighbors_both", "neighbor_count",
               "ci95_low_earlier", "ci95_high_earlier", "ci95_low_later", "ci95_high_later",
               "provisional_pass", "strict_robust_pass"]
    text = f"""# Stage 1.5 v2 — Strict Robustness Audit

## Scope

This audit uses the realistic long-only spot execution model: one position, 10 bps fee and 2 bps adverse slippage per side, +4% target, -4% stop, 24-hour maximum hold, and conservative same-minute stop priority. It compares the refined 3-minute bearish-filter candidate, the original 5-minute control, and the smaller 5-minute rising-average candidate.

## Final candidate comparison

{markdown(summary[columns])}

## Quarter-by-quarter results

{markdown(quarters)}

## Nearby-parameter results

{markdown(neighbors)}

## Decision

- Provisional passes before the confidence requirement: {int(summary.provisional_pass.sum())}.
- Strict robust passes: {int(summary.strict_robust_pass.sum())}.
- Protected earlier files verified unchanged: {protected_count:,}.

A strict pass requires enough independent trades in both periods, positive mean and median returns, at least 60% positive quarters, worst trade and expected shortfall above -5%, compounded drawdown above -20%, majority support from adjacent timeframes/zones, and positive lower 95% seven-day-block confidence bounds in both periods.

The later historical period is already observed and cannot replace official Stage 2 forward validation. Drawdown assumes equal-notional returns are compounded sequentially and is a comparison measure rather than a proposed portfolio sizing model.
"""
    (path / "strict_robustness_report.md").write_text(text)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = np.arange(len(summary)); width = .36
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x - width / 2, summary.mean_pct_earlier, width, label="Earlier")
    ax.bar(x + width / 2, summary.mean_pct_later, width, label="Later")
    ax.errorbar(x - width / 2, summary.mean_pct_earlier,
                yerr=[summary.mean_pct_earlier - summary.ci95_low_earlier,
                      summary.ci95_high_earlier - summary.mean_pct_earlier], fmt="none", color="black", capsize=3)
    ax.errorbar(x + width / 2, summary.mean_pct_later,
                yerr=[summary.mean_pct_later - summary.ci95_low_later,
                      summary.ci95_high_later - summary.mean_pct_later], fmt="none", color="black", capsize=3)
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xticks(x, summary.candidate.str.replace("_", "\n"), fontsize=9)
    ax.set_ylabel("Mean realistic spot return (%)")
    ax.set_title("Final candidates with 95% block-bootstrap intervals")
    ax.legend(); fig.tight_layout()
    fig.savefig(path / "strict_candidate_comparison.png", dpi=160)
    plt.close(fig)

