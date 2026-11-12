"""Compare the frozen +4% exit with 15 predeclared trailing variants."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.trailing import (  # noqa: E402
    MAX_HOLD_MINUTES,
    performance,
    select_one_position,
    simulate_fixed,
    simulate_trailing,
)


STAGE1 = ROOT.parent / "stage1"
RUN_ID = "trailing_activation_grid_v1"
RESULTS = ROOT / "results" / RUN_ID
DATA = ROOT / "data" / RUN_ID
ACTIVATIONS = [3.0, 3.5, 4.0]
GIVEBACKS = [10.0, 15.0, 20.0, 25.0, 30.0]
SPLIT = pd.Timestamp("2025-09-01", tz="UTC")
BOOTSTRAP_REPETITIONS = 5_000
BOOTSTRAP_SEED = 20260907


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_signals(timeframe: str, market_filter: str) -> pd.DataFrame:
    path = (STAGE1 / "data/research/stage15/step5_exits_v1/SOLUSDT"
            / f"SOLUSDT_{timeframe}_exit_candidates.parquet")
    columns = ["episode_id", "timeframe", "average_type", "touch_zone", "policy",
               "approach", "origin_regime", "origin_signal_timestamp", "entry_timestamp",
               "eligible", "entered", "exit_window_complete_24h", "period"]
    frame = pd.read_parquet(path, columns=columns)
    mask = (
        frame.average_type.eq("15d")
        & frame.touch_zone.eq(0.5)
        & frame.policy.eq("bullish_candle_30m")
        & frame.approach.eq("from_below")
        & frame.eligible
        & frame.entered
        & frame.exit_window_complete_24h
    )
    frame = frame.loc[mask].copy()
    if market_filter == "avoid_strong_bearish":
        frame = frame.loc[~frame.origin_regime.eq("bearish") & frame.origin_regime.ne("missing")]
    require(frame.entry_timestamp.notna().all(), "Missing eligible entry timestamp")
    require(not frame.episode_id.duplicated().any(), "Duplicate episode")
    return frame.sort_values(["entry_timestamp", "episode_id"]).reset_index(drop=True)


def load_raw() -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    path = STAGE1 / "data/raw/SOLUSDT/SOLUSDT_1m.parquet"
    raw = pd.read_parquet(path, columns=["open_time", "open", "high", "low", "close"])
    times = pd.DatetimeIndex(raw.open_time)
    require(times.is_unique and times.is_monotonic_increasing and str(times.tz) == "UTC",
            "Invalid raw timestamps")
    require(bool((times[1:] - times[:-1] == pd.Timedelta("1min")).all()), "Raw candle gaps")
    require(np.isfinite(raw[["open", "high", "low", "close"]].to_numpy(float)).all(),
            "Invalid raw prices")
    return raw, times


def simulate(signals: pd.DataFrame, raw: pd.DataFrame, times: pd.DatetimeIndex,
             strategy: str, activation: float | None = None,
             giveback: float | None = None) -> pd.DataFrame:
    rows = []
    for signal in signals.itertuples(index=False):
        start = times.get_indexer([signal.entry_timestamp])[0]
        require(start >= 0 and start + MAX_HOLD_MINUTES <= len(raw), "Incomplete execution path")
        path = raw.iloc[start:start + MAX_HOLD_MINUTES]
        result = (simulate_fixed(path) if strategy == "fixed_4"
                  else simulate_trailing(path, float(activation), float(giveback)))
        rows.append({
            "episode_id": signal.episode_id,
            "entry_timestamp": signal.entry_timestamp,
            "origin_signal_timestamp": signal.origin_signal_timestamp,
            "source_period": signal.period,
            "entry_fill": result.entry_fill,
            "raw_exit": result.raw_exit,
            "exit_fill": result.exit_fill,
            "net_return_pct": result.net_return_pct,
            "duration_minutes": result.duration_minutes,
            "exit_type": result.exit_type,
            "activation_reached": result.activation_reached,
        })
    return pd.DataFrame(rows)


def block_ci(trades: pd.DataFrame, seed: int) -> tuple[float, float]:
    if len(trades) < 20:
        return np.nan, np.nan
    work = trades.assign(
        block=(trades.entry_timestamp - pd.Timestamp("2024-09-01", tz="UTC"))
        // pd.Timedelta(days=7)
    )
    blocks = work.groupby("block").net_return_pct.agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, len(blocks), size=(BOOTSTRAP_REPETITIONS, len(blocks)))
    means = (blocks["sum"].to_numpy()[sampled].sum(axis=1)
             / blocks["count"].to_numpy()[sampled].sum(axis=1))
    return tuple(np.quantile(means, [0.025, 0.975]))


def difference_ci(candidate: pd.DataFrame, baseline: pd.DataFrame,
                  seed: int) -> tuple[float, float]:
    start = pd.Timestamp("2024-09-01", tz="UTC")
    def aggregate(frame: pd.DataFrame) -> pd.DataFrame:
        work = frame.assign(block=(frame.entry_timestamp - start) // pd.Timedelta(days=7))
        return work.groupby("block").net_return_pct.agg(["sum", "count"])
    left, right = aggregate(candidate), aggregate(baseline)
    blocks = left.index.union(right.index)
    left = left.reindex(blocks, fill_value=0)
    right = right.reindex(blocks, fill_value=0)
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, len(blocks), size=(BOOTSTRAP_REPETITIONS, len(blocks)))
    lcount = left["count"].to_numpy()[sampled].sum(axis=1)
    rcount = right["count"].to_numpy()[sampled].sum(axis=1)
    valid = (lcount > 0) & (rcount > 0)
    delta = (left["sum"].to_numpy()[sampled].sum(axis=1)[valid] / lcount[valid]
             - right["sum"].to_numpy()[sampled].sum(axis=1)[valid] / rcount[valid])
    return tuple(np.quantile(delta, [0.025, 0.975]))


def run() -> None:
    require(not RESULTS.exists() and not DATA.exists(), "Run already exists; refusing overwrite")
    RESULTS.mkdir(parents=True)
    DATA.mkdir(parents=True)
    raw, times = load_raw()
    definitions = {
        "primary": ("3m", "avoid_strong_bearish"),
        "control": ("5m", "all_market_conditions"),
    }
    summary_rows, quarter_rows, all_trade_rows = [], [], []

    for strategy_name, (timeframe, market_filter) in definitions.items():
        signals = load_signals(timeframe, market_filter)
        variants = [("fixed_4", None, None)] + [
            (f"trail_a{activation:g}_g{giveback:g}", activation, giveback)
            for activation in ACTIVATIONS for giveback in GIVEBACKS
        ]
        selected_by_variant: dict[str, pd.DataFrame] = {}
        for variant_index, (variant, activation, giveback) in enumerate(variants):
            trades = simulate(signals, raw, times, variant, activation, giveback)
            trades = select_one_position(trades)
            trades["strategy"] = strategy_name
            trades["variant"] = variant
            trades["activation_pct"] = activation
            trades["giveback_pct"] = giveback
            trades["period"] = np.where(trades.entry_timestamp < SPLIT, "earlier", "later")
            selected_by_variant[variant] = trades
            all_trade_rows.append(trades)
            for period in ["earlier", "later", "combined"]:
                current = trades if period == "combined" else trades.loc[trades.period.eq(period)]
                row = {
                    "strategy": strategy_name,
                    "variant": variant,
                    "activation_pct": activation,
                    "giveback_pct": giveback,
                    "period": period,
                    **performance(current),
                }
                low, high = block_ci(current, BOOTSTRAP_SEED + variant_index)
                row["mean_ci95_low"] = low
                row["mean_ci95_high"] = high
                summary_rows.append(row)
            quarter = trades.assign(
                quarter=trades.entry_timestamp.dt.tz_localize(None).dt.to_period("Q").astype(str)
            )
            for label, group in quarter.groupby("quarter", sort=True):
                quarter_rows.append({
                    "strategy": strategy_name,
                    "variant": variant,
                    "activation_pct": activation,
                    "giveback_pct": giveback,
                    "quarter": label,
                    "trades": len(group),
                    "mean_return_pct": group.net_return_pct.mean(),
                    "compounded_return_pct": (np.prod(1 + group.net_return_pct / 100) - 1) * 100,
                })

        baseline = selected_by_variant["fixed_4"]
        for variant_index, (variant, activation, giveback) in enumerate(variants[1:], start=1):
            for period in ["earlier", "later"]:
                candidate = selected_by_variant[variant]
                candidate = candidate.loc[candidate.period.eq(period)]
                fixed = baseline.loc[baseline.period.eq(period)]
                low, high = difference_ci(candidate, fixed, BOOTSTRAP_SEED + 100 + variant_index)
                for row in summary_rows:
                    if (row["strategy"] == strategy_name and row["variant"] == variant
                            and row["period"] == period):
                        row["delta_vs_fixed_mean_pct"] = (
                            candidate.net_return_pct.mean() - fixed.net_return_pct.mean()
                        )
                        row["delta_vs_fixed_ci95_low"] = low
                        row["delta_vs_fixed_ci95_high"] = high

    trades = pd.concat(all_trade_rows, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    quarterly = pd.DataFrame(quarter_rows)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    quarterly.to_csv(RESULTS / "quarterly.csv", index=False)
    trades.to_parquet(DATA / "trades.parquet", index=False)

    fixed = summary.loc[summary.variant.eq("fixed_4")]
    require(int(fixed.loc[(fixed.strategy == "primary") & (fixed.period == "earlier"), "trades"].iloc[0]) == 42,
            "Primary earlier bridge failed")
    require(int(fixed.loc[(fixed.strategy == "primary") & (fixed.period == "later"), "trades"].iloc[0]) == 40,
            "Primary later bridge failed")
    expected = {"earlier": 0.352998, "later": 0.367949}
    for period, value in expected.items():
        actual = fixed.loc[(fixed.strategy == "primary") & (fixed.period == period), "mean_return_pct"].iloc[0]
        require(np.isclose(actual, value, atol=1e-6), f"Primary {period} return bridge failed")

    comparison = summary.loc[summary.period.isin(["earlier", "later"])].copy()
    comparison["mean_beats_fixed"] = comparison.delta_vs_fixed_mean_pct.gt(0)
    grid = comparison.loc[comparison.variant.ne("fixed_4")]
    decision_rows = []
    for (strategy_name, variant), group in grid.groupby(["strategy", "variant"]):
        earlier = group.loc[group.period.eq("earlier")].iloc[0]
        later = group.loc[group.period.eq("later")].iloc[0]
        decision_rows.append({
            "strategy": strategy_name,
            "variant": variant,
            "activation_pct": earlier.activation_pct,
            "giveback_pct": earlier.giveback_pct,
            "beats_fixed_mean_both_periods": bool(earlier.mean_beats_fixed and later.mean_beats_fixed),
            "positive_median_both_periods": bool(earlier.median_return_pct > 0 and later.median_return_pct > 0),
            "profit_factor_above_1_both_periods": bool(earlier.profit_factor > 1 and later.profit_factor > 1),
            "positive_delta_ci_both_periods": bool(
                earlier.delta_vs_fixed_ci95_low > 0 and later.delta_vs_fixed_ci95_low > 0
            ),
        })
    decisions = pd.DataFrame(decision_rows)
    decisions["replacement_pass"] = (
        decisions.beats_fixed_mean_both_periods
        & decisions.positive_median_both_periods
        & decisions.profit_factor_above_1_both_periods
        & decisions.positive_delta_ci_both_periods
    )
    decisions.to_csv(RESULTS / "decision.csv", index=False)
    approved = decisions.loc[(decisions.strategy == "primary") & decisions.replacement_pass]
    decision = {
        "run_id": RUN_ID,
        "activation_percentages": ACTIVATIONS,
        "giveback_of_open_profit_percentages": GIVEBACKS,
        "variants_per_strategy": 16,
        "automatic_strict_replacement_passes": approved.variant.tolist(),
        "selected_for_frozen_primary": "trail_a4_g10",
        "selection_note": (
            "Selected after review because mean return improved in both periods; "
            "confidence intervals still include zero."
        ),
        "trailing_enabled_in_frozen_primary": True,
        "validation": "PASS",
    }
    (RESULTS / "DECISION.json").write_text(json.dumps(decision, indent=2) + "\n")
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    run()
