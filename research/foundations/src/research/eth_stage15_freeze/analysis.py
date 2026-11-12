"""Dependence-aware ETH candidate analysis built on audited Stage 1.5 events."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.research.stage15_robustness.analysis import (
    condition_mask,
    expected_shortfall_10,
    max_drawdown_pct,
    quarter_labels,
    select_nonoverlap,
)


SCENARIOS = {
    "gross": (0.0, 0.0),
    "fee_only": (10.0, 0.0),
    "realistic": (10.0, 2.0),
    "stressed": (10.0, 5.0),
    "severe": (10.0, 10.0),
}
CONDITIONS = ["all_entries", "bullish_regime", "from_below", "rising_average"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def execution_adjusted_return(
    gross_return_pct: pd.Series | np.ndarray,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
) -> np.ndarray:
    """Apply adverse spot fills and entry/exit fees to an existing raw-fill return.

    This preserves the already audited exit event. The final frozen rule uses a
    time exit, so only the protective-stop boundary can differ slightly when
    actual fill slippage is introduced; stressed scenarios cover that uncertainty.
    """
    gross_multiple = 1.0 + np.asarray(gross_return_pct, dtype=float) / 100.0
    fee = fee_bps_per_side / 10_000.0
    slip = slippage_bps_per_side / 10_000.0
    net_multiple = gross_multiple * (1.0 - slip) / (1.0 + slip)
    net_multiple *= (1.0 - fee) / (1.0 + fee)
    return (net_multiple - 1.0) * 100.0


def longest_nonpositive_streak(values: Iterable[float]) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value <= 0 else 0
        longest = max(longest, current)
    return longest


def profit_factor(values: pd.Series) -> float:
    wins = values.loc[values > 0].sum()
    losses = -values.loc[values < 0].sum()
    if losses == 0:
        return np.inf if wins > 0 else np.nan
    return float(wins / losses)


def block_bootstrap(
    frame: pd.DataFrame,
    return_column: str,
    repetitions: int,
    seed: int,
) -> dict[str, float | int]:
    if len(frame) < 30:
        return {"ci95_low": np.nan, "ci95_high": np.nan, "probability_mean_positive_pct": np.nan, "blocks": 0}
    blocks = (
        (frame.origin_signal_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
        // pd.Timedelta(days=7)
    )
    stats = pd.DataFrame({"block": blocks, "value": frame[return_column]}).groupby("block").value.agg(["sum", "count"])
    if len(stats) < 8:
        return {"ci95_low": np.nan, "ci95_high": np.nan, "probability_mean_positive_pct": np.nan, "blocks": len(stats)}
    rng = np.random.default_rng(seed)
    sample_indices = rng.integers(0, len(stats), size=(repetitions, len(stats)))
    sampled_means = (
        stats["sum"].to_numpy()[sample_indices].sum(axis=1)
        / stats["count"].to_numpy()[sample_indices].sum(axis=1)
    )
    low, high = np.quantile(sampled_means, [0.025, 0.975])
    return {
        "ci95_low": float(low),
        "ci95_high": float(high),
        "probability_mean_positive_pct": float((sampled_means > 0).mean() * 100),
        "blocks": len(stats),
    }


def selected_events(
    candidates: pd.DataFrame,
    timeframe: str,
    average_type: str,
    touch_zone: float,
    policy: str,
    condition: str,
    strategy: str,
) -> pd.DataFrame:
    frame = candidates.loc[
        candidates.timeframe.eq(timeframe)
        & candidates.average_type.eq(average_type)
        & candidates.touch_zone.eq(touch_zone)
        & candidates.policy.eq(policy)
        & candidates.eligible
        & candidates.entered
        & candidates.exit_window_complete_24h
    ].copy()
    frame = frame.loc[condition_mask(frame, condition)]
    return_column = f"{strategy}_return_pct"
    duration_column = f"{strategy}_duration_minutes"
    selected = []
    for period in ["earlier", "later"]:
        current = frame.loc[frame.period.eq(period)]
        chosen = select_nonoverlap(current, duration_column).copy()
        chosen["analysis_period"] = period
        selected.append(chosen)
    return pd.concat(selected).sort_values(["entry_timestamp", "episode_id"])


def candidate_signals(
    candidates: pd.DataFrame,
    timeframe: str = "3m",
    average_type: str = "15d",
    touch_zone: float = 1.0,
    policy: str = "bullish_candle_30m",
    condition: str = "bullish_regime",
) -> pd.DataFrame:
    frame = candidates.loc[
        candidates.timeframe.eq(timeframe)
        & candidates.average_type.eq(average_type)
        & candidates.touch_zone.eq(touch_zone)
        & candidates.policy.eq(policy)
        & candidates.eligible
        & candidates.entered
        & candidates.exit_window_complete_24h
    ].copy()
    return frame.loc[condition_mask(frame, condition)]


def simulate_exact_time_stop(
    signals: pd.DataFrame,
    raw: pd.DataFrame,
    fee_bps_per_side: float,
    slippage_bps_per_side: float,
    hold_minutes: int = 480,
    stop_pct: float = 4.0,
) -> pd.DataFrame:
    """Replay a long spot time exit and stop from actual adverse entry fills."""
    times = pd.DatetimeIndex(raw.open_time)
    require(times.is_unique and times.is_monotonic_increasing and str(times.tz) == "UTC", "Invalid raw times")
    require((times[1:] - times[:-1] == pd.Timedelta("1min")).all(), "Raw one-minute gaps")
    starts = times.get_indexer(pd.DatetimeIndex(signals.entry_timestamp))
    require((starts >= 0).all(), "Entry missing from raw candles")
    require((starts + hold_minutes - 1 < len(raw)).all(), "Incomplete execution window")
    opened = raw.open.to_numpy(float)
    lows = raw.low.to_numpy(float)
    closes = raw.close.to_numpy(float)
    raw_entry = opened[starts]
    fee = fee_bps_per_side / 10_000.0
    slip = slippage_bps_per_side / 10_000.0
    entry_fill = raw_entry * (1.0 + slip)
    stop_price = entry_fill * (1.0 - stop_pct / 100.0)
    offsets = np.arange(hold_minutes)
    indices = starts[:, None] + offsets
    hit_mask = lows[indices] <= stop_price[:, None]
    stop_hit = hit_mask.any(axis=1)
    stop_offset = np.where(stop_hit, hit_mask.argmax(axis=1), hold_minutes - 1)
    stop_indices = starts + stop_offset
    stop_market = np.minimum(stop_price, opened[stop_indices])
    time_market = closes[starts + hold_minutes - 1]
    raw_exit = np.where(stop_hit, stop_market, time_market)
    exit_fill = raw_exit * (1.0 - slip)
    net_multiple = exit_fill * (1.0 - fee) / (entry_fill * (1.0 + fee))
    result = signals.copy()
    result["entry_fill"] = entry_fill
    result["exit_fill"] = exit_fill
    result["net_return_pct"] = (net_multiple - 1.0) * 100.0
    result["exact_duration_minutes"] = np.where(stop_hit, stop_offset + 1, hold_minutes)
    result["exact_exit_type"] = np.where(stop_hit, "protective_stop", "time")
    return result


def exact_scenario_events(
    candidates: pd.DataFrame,
    raw: pd.DataFrame,
    stop_pct: float = 5.0,
) -> pd.DataFrame:
    signals = candidate_signals(candidates)
    frames = []
    for scenario, (fee_bps, slip_bps) in SCENARIOS.items():
        replayed = simulate_exact_time_stop(signals, raw, fee_bps, slip_bps, stop_pct=stop_pct)
        selected = []
        for period in ["earlier", "later"]:
            current = replayed.loc[replayed.period.eq(period)]
            chosen = select_nonoverlap(current, "exact_duration_minutes").copy()
            chosen["analysis_period"] = period
            selected.append(chosen)
        scenario_frame = pd.concat(selected)
        scenario_frame["scenario"] = scenario
        frames.append(scenario_frame)
    return pd.concat(frames, ignore_index=True).sort_values(["scenario", "entry_timestamp", "episode_id"])


def scenario_metrics(
    events: pd.DataFrame,
    repetitions: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    quarters: list[dict] = []
    months: list[dict] = []
    for scenario, (fee_bps, slip_bps) in SCENARIOS.items():
        current = events.loc[events.scenario.eq(scenario)].copy()
        for period in ["earlier", "later", "combined"]:
            part = current if period == "combined" else current.loc[current.analysis_period.eq(period)]
            values = part.net_return_pct
            bootstrap = block_bootstrap(part, "net_return_pct", repetitions, seed)
            rows.append({
                "scenario": scenario,
                "period": period,
                "fee_bps_per_side": fee_bps,
                "slippage_bps_per_side": slip_bps,
                "trades": len(part),
                "mean_pct": values.mean(),
                "median_pct": values.median(),
                "positive_pct": values.gt(0).mean() * 100 if len(values) else np.nan,
                "profit_factor": profit_factor(values),
                "expected_shortfall_10_pct": expected_shortfall_10(values),
                "worst_trade_pct": values.min(),
                "max_compounded_drawdown_pct": max_drawdown_pct(values),
                "longest_nonpositive_streak": longest_nonpositive_streak(values),
                **bootstrap,
            })
        detailed = current.assign(
            quarter=quarter_labels(current.origin_signal_timestamp),
            month=current.origin_signal_timestamp.dt.strftime("%Y-%m"),
        )
        for quarter, group in detailed.groupby("quarter", sort=True):
            quarters.append({"scenario": scenario, "quarter": quarter, "trades": len(group),
                             "mean_pct": group.net_return_pct.mean(), "median_pct": group.net_return_pct.median(),
                             "positive_pct": group.net_return_pct.gt(0).mean() * 100})
        for month, group in detailed.groupby("month", sort=True):
            months.append({"scenario": scenario, "month": month, "trades": len(group),
                           "mean_pct": group.net_return_pct.mean(), "sum_pct": group.net_return_pct.sum()})
    return pd.DataFrame(rows), pd.DataFrame(quarters), pd.DataFrame(months)


def sensitivity_table(
    candidates: pd.DataFrame,
    raw: pd.DataFrame,
    repetitions: int,
    seed: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    for timeframe in ["1m", "3m", "5m"]:
        for zone in [0.5, 1.0, 1.5]:
            signals = candidate_signals(candidates, timeframe, "15d", zone)
            replayed = simulate_exact_time_stop(signals, raw, 10.0, 2.0, stop_pct=5.0)
            row = {"timeframe": timeframe, "touch_zone_pct": zone}
            for period in ["earlier", "later"]:
                part = select_nonoverlap(
                    replayed.loc[replayed.period.eq(period)], "exact_duration_minutes"
                ).copy()
                part["realistic_return_pct"] = part.net_return_pct
                boot = block_bootstrap(part, "realistic_return_pct", repetitions, seed)
                row[f"trades_{period}"] = len(part)
                row[f"mean_pct_{period}"] = part.realistic_return_pct.mean()
                row[f"median_pct_{period}"] = part.realistic_return_pct.median()
                row[f"ci95_low_{period}"] = boot["ci95_low"]
            rows.append(row)
    return pd.DataFrame(rows)


def exact_stop_sensitivity(candidates: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    signals = candidate_signals(candidates)
    rows = []
    for stop_pct in [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]:
        replayed = simulate_exact_time_stop(signals, raw, 10.0, 2.0, stop_pct=stop_pct)
        row = {"protective_stop_pct": stop_pct}
        for period in ["earlier", "later"]:
            selected = select_nonoverlap(
                replayed.loc[replayed.period.eq(period)], "exact_duration_minutes"
            )
            values = selected.net_return_pct
            row[f"trades_{period}"] = len(selected)
            row[f"mean_pct_{period}"] = values.mean()
            row[f"median_pct_{period}"] = values.median()
            row[f"worst_trade_pct_{period}"] = values.min()
            row[f"expected_shortfall_10_pct_{period}"] = expected_shortfall_10(values)
            row[f"max_drawdown_pct_{period}"] = max_drawdown_pct(values)
        row["worst_period_mean_pct"] = min(row["mean_pct_earlier"], row["mean_pct_later"])
        rows.append(row)
    return pd.DataFrame(rows)


def exit_sweep(
    candidates: pd.DataFrame,
    strategies: list[str],
) -> pd.DataFrame:
    rows: list[dict] = []
    for strategy in strategies:
        events = selected_events(
            candidates, "3m", "15d", 1.0,
            "bullish_candle_30m", "bullish_regime", strategy,
        )
        realistic = execution_adjusted_return(events[f"{strategy}_return_pct"], 10.0, 2.0)
        current = events.assign(realistic_return_pct=realistic)
        row = {"strategy": strategy}
        for period in ["earlier", "later"]:
            part = current.loc[current.analysis_period.eq(period)]
            row[f"trades_{period}"] = len(part)
            row[f"mean_pct_{period}"] = part.realistic_return_pct.mean()
            row[f"median_pct_{period}"] = part.realistic_return_pct.median()
            row[f"expected_shortfall_10_pct_{period}"] = expected_shortfall_10(part.realistic_return_pct)
            row[f"max_drawdown_pct_{period}"] = max_drawdown_pct(part.realistic_return_pct)
        row["worst_period_mean_pct"] = min(row["mean_pct_earlier"], row["mean_pct_later"])
        rows.append(row)
    return pd.DataFrame(rows).sort_values("worst_period_mean_pct", ascending=False).reset_index(drop=True)


def evaluate_decision(
    metrics: pd.DataFrame,
    quarters: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> dict[str, bool | float | str]:
    realistic = metrics.loc[metrics.scenario.eq("realistic")].set_index("period")
    main_neighbors = sensitivity.loc[
        sensitivity.touch_zone_pct.eq(1.0) & sensitivity.timeframe.isin(["1m", "5m"])
    ]
    realistic_quarters = quarters.loc[quarters.scenario.eq("realistic")]
    positive_quarters_pct = realistic_quarters.mean_pct.gt(0).mean() * 100
    sample_pass = all(realistic.loc[p, "trades"] >= 40 for p in ["earlier", "later"])
    mean_pass = all(realistic.loc[p, "mean_pct"] > 0 for p in ["earlier", "later"])
    neighbor_positive_both = main_neighbors[
        ["mean_pct_earlier", "mean_pct_later"]
    ].gt(0).all(axis=1)
    neighbor_pass = len(main_neighbors) >= 2 and neighbor_positive_both.mean() >= 0.5
    quarter_pass = positive_quarters_pct >= 60
    tail_pass = all(
        realistic.loc[p, "expected_shortfall_10_pct"] >= -5.25
        and realistic.loc[p, "worst_trade_pct"] >= -5.25
        and realistic.loc[p, "max_compounded_drawdown_pct"] >= -20
        for p in ["earlier", "later"]
    )
    paper_pass = sample_pass and mean_pass and neighbor_pass and quarter_pass and tail_pass
    median_pass = all(realistic.loc[p, "median_pct"] > 0 for p in ["earlier", "later"])
    ci_pass = all(realistic.loc[p, "ci95_low"] > 0 for p in ["earlier", "later"])
    strict_pass = paper_pass and median_pass and ci_pass
    return {
        "sample_pass": bool(sample_pass),
        "realistic_mean_positive_both_periods": bool(mean_pass),
        "adjacent_timeframes_positive_both_periods": bool(neighbor_pass),
        "positive_adjacent_timeframes": int(neighbor_positive_both.sum()),
        "adjacent_timeframes_tested": int(len(main_neighbors)),
        "positive_quarters_pct": float(positive_quarters_pct),
        "quarter_consistency_pass": bool(quarter_pass),
        "tail_and_drawdown_pass": bool(tail_pass),
        "realistic_median_positive_both_periods": bool(median_pass),
        "positive_block_ci_both_periods": bool(ci_pass),
        "paper_freeze_pass": bool(paper_pass),
        "strict_historical_validation_pass": bool(strict_pass),
        "decision": "HISTORICALLY_VALIDATED" if strict_pass else (
            "FROZEN_FOR_PAPER_VALIDATION_ONLY" if paper_pass else "REJECTED"
        ),
    }
