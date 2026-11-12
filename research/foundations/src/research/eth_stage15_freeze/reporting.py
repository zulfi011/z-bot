"""Human-readable report for the ETH Stage 1.5 freeze decision."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def fmt(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:.4f}"


def write_report(
    path: Path,
    metrics: pd.DataFrame,
    quarters: pd.DataFrame,
    sensitivity: pd.DataFrame,
    stop_sensitivity: pd.DataFrame,
    exits: pd.DataFrame,
    decision: dict,
) -> None:
    realistic = metrics.loc[metrics.scenario.eq("realistic")].set_index("period")
    scenarios = metrics.loc[metrics.period.eq("combined")]
    main_neighbors = sensitivity.loc[sensitivity.touch_zone_pct.eq(1.0)]
    realistic_quarters = quarters.loc[quarters.scenario.eq("realistic")]
    lines = [
        "# ETH Stage 1.5 Full Historical Audit and Freeze Decision",
        "",
        "## Decision",
        "",
        f"**{decision['decision']}**",
        "",
        "The candidate is frozen as an immutable paper-trading hypothesis only. It is not approved for live trading because the historical sample was used to select it, realistic medians are not positive in both periods, and both 95% block-bootstrap intervals include zero.",
        "",
        "## Frozen strategy",
        "",
        "- ETHUSDT spot, long only, one open position maximum.",
        "- Use 3-minute signal candles and raw 1-minute execution candles.",
        "- Calculate 7D, 15D, and 30D simple averages from completed UTC daily closes only.",
        "- Eligible regime: 7D average > 15D average > 30D average.",
        "- Start one touch episode when a 3-minute candle range intersects the ±1.0% zone around the 15D average; consecutive touching candles remain one episode.",
        "- During that episode, accept the first bullish 3-minute candle (close > open) no later than 30 minutes after the first touch. The first non-touch candle is the final confirmation opportunity.",
        "- Enter at the next raw 1-minute open after the confirming candle closes.",
        "- Place a 5.0% protective stop from the actual entry fill; a gap fills at the worse of the stop or candle open.",
        "- No profit target and no trailing stop. Exit after 480 minutes using the final raw 1-minute close, with adverse exit slippage.",
        "- Risk at most 1.0% of current net liquidation per trade. With a modeled 5.25% all-in stop loss, cap position notional at 19.0% of net liquidation; use spot balance only and no leverage.",
        "- Model 10 bps fee and 2 bps slippage per side. Reject paper signals if the implementation cannot preserve these rules.",
        "",
        "## Main candidate by historical period",
        "",
        "| period | trades | mean % | median % | win % | profit factor | ES 10% | max DD % | 95% CI | P(mean > 0) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for period in ["earlier", "later", "combined"]:
        row = realistic.loc[period]
        lines.append(
            f"| {period} | {int(row.trades)} | {fmt(row.mean_pct)} | {fmt(row.median_pct)} | "
            f"{fmt(row.positive_pct)} | {fmt(row.profit_factor)} | {fmt(row.expected_shortfall_10_pct)} | "
            f"{fmt(row.max_compounded_drawdown_pct)} | [{fmt(row.ci95_low)}, {fmt(row.ci95_high)}] | "
            f"{fmt(row.probability_mean_positive_pct)}% |"
        )
    lines += [
        "",
        "The earlier/later boundary is 2025-09-01 UTC. Returns include 10 bps fees and 2 bps slippage on each side.",
        "The main statistics use an exact raw-minute replay with the protective stop calculated from the adverse entry fill. The broader exit sweep preserves each previously audited historical exit event and overlays execution costs for comparison.",
        "",
        "## Execution-cost sensitivity",
        "",
        "| scenario | fee/side bps | slippage/side bps | combined mean % | combined median % | profit factor | max DD % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in scenarios.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.fee_bps_per_side:.1f} | {row.slippage_bps_per_side:.1f} | "
            f"{fmt(row.mean_pct)} | {fmt(row.median_pct)} | {fmt(row.profit_factor)} | "
            f"{fmt(row.max_compounded_drawdown_pct)} |"
        )
    lines += [
        "",
        "## Adjacent timeframe and zone sensitivity",
        "",
        "| timeframe | zone % | trades earlier/later | mean earlier % | mean later % | median earlier % | median later % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sensitivity.itertuples(index=False):
        lines.append(
            f"| {row.timeframe} | {row.touch_zone_pct:.1f} | {int(row.trades_earlier)}/{int(row.trades_later)} | "
            f"{fmt(row.mean_pct_earlier)} | {fmt(row.mean_pct_later)} | "
            f"{fmt(row.median_pct_earlier)} | {fmt(row.median_pct_later)} |"
        )
    lines += [
        "",
        "At the frozen ±1.0% zone, the 1m variant retains positive means in both periods. The 5m variant is positive earlier and −0.0143% later. One of two adjacent timeframes therefore passes the predeclared 50% continuity threshold; neither neighbor has a positive confidence lower bound.",
        "",
        "## Exact protective-stop sensitivity",
        "",
        "| stop % | trades earlier/later | mean earlier % | mean later % | worst earlier % | worst later % | max DD earlier % | max DD later % |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stop_sensitivity.itertuples(index=False):
        lines.append(
            f"| {row.protective_stop_pct:.1f} | {int(row.trades_earlier)}/{int(row.trades_later)} | "
            f"{fmt(row.mean_pct_earlier)} | {fmt(row.mean_pct_later)} | "
            f"{fmt(row.worst_trade_pct_earlier)} | {fmt(row.worst_trade_pct_later)} | "
            f"{fmt(row.max_drawdown_pct_earlier)} | {fmt(row.max_drawdown_pct_later)} |"
        )
    lines += [
        "",
        "The exact fill replay rejects stops from 2% through 4% because their realistic mean is non-positive in at least one period. The 5% stop is the smallest tested protective boundary that preserves a positive mean in both periods. This choice was made on historical data and is therefore part of the strategy's selection bias; it must remain unchanged during prospective paper validation.",
        "",
        "## Exit sweep",
        "",
        "Top ten of all 38 previously audited exit rules for the same 3m/15D/±1.0% entry family, ranked by the weaker realistic period mean:",
        "",
        "| exit | trades earlier/later | mean earlier % | mean later % | median earlier % | median later % | weaker mean % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in exits.head(10).itertuples(index=False):
        lines.append(
            f"| {row.strategy} | {int(row.trades_earlier)}/{int(row.trades_later)} | "
            f"{fmt(row.mean_pct_earlier)} | {fmt(row.mean_pct_later)} | "
            f"{fmt(row.median_pct_earlier)} | {fmt(row.median_pct_later)} | "
            f"{fmt(row.worst_period_mean_pct)} |"
        )
    positive_quarters = realistic_quarters.mean_pct.gt(0).sum()
    lines += [
        "",
        "## Gate audit",
        "",
        f"- Sample size: **{'PASS' if decision['sample_pass'] else 'FAIL'}**.",
        f"- Positive realistic mean in both periods: **{'PASS' if decision['realistic_mean_positive_both_periods'] else 'FAIL'}**.",
        f"- At least half of adjacent timeframes positive in both periods: **{'PASS' if decision['adjacent_timeframes_positive_both_periods'] else 'FAIL'}** ({decision['positive_adjacent_timeframes']}/{decision['adjacent_timeframes_tested']}).",
        f"- Positive-quarter consistency: **{'PASS' if decision['quarter_consistency_pass'] else 'FAIL'}** ({positive_quarters}/{len(realistic_quarters)} quarters; {decision['positive_quarters_pct']:.2f}%).",
        f"- Tail and drawdown floors: **{'PASS' if decision['tail_and_drawdown_pass'] else 'FAIL'}**.",
        f"- Positive realistic median in both periods: **{'PASS' if decision['realistic_median_positive_both_periods'] else 'FAIL'}**.",
        f"- Positive 95% weekly-block confidence lower bound in both periods: **{'PASS' if decision['positive_block_ci_both_periods'] else 'FAIL'}**.",
        "",
        "Passing the paper-freeze gate means the rule is sufficiently coherent to test prospectively without further historical tuning. Failing the strict gate means the historical evidence does not establish a dependable positive edge.",
        "",
        "## Interpretation",
        "",
        "This is a small, positively skewed historical effect. Its gross return is only slightly larger than realistic round-trip execution drag, and it becomes fragile under stressed slippage. Paper trading must measure actual fill drag, missed signals, stop gaps, and data latency. The frozen parameters must not be tuned during that test; any rule change creates a new version and restarts validation.",
        "",
        "## Reproduction",
        "",
        "Run from `research/foundations`: `.env/bin/python -B -m src.research.eth_stage15_freeze.run`.",
    ]
    path.write_text("\n".join(lines) + "\n")
