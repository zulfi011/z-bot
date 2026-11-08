"""Generate and validate frozen primary/control entries chronologically."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.engine import ChronologicalBacktester  # noqa: E402
from src.backtesting.entries import EntryReplayStrategy, SignalFeed, SignalSpec  # noqa: E402


STAGE1 = ROOT.parent / "stage1_research"
RUN_ID = "step3_entries_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
CONFIG = ROOT / "config/strategies/sol_15d_touch_v1.yaml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def load_config() -> tuple[dict[str, SignalSpec], float]:
    config = yaml.safe_load(CONFIG.read_text())
    require(config["specification"]["status"] == "frozen_for_stage2", "Strategy is not frozen")
    specs = {}
    for name in ["primary", "control"]:
        source = config["strategies"][name]
        require(source["asset"] == "SOLUSDT", "Step 3 supports the frozen SOL asset")
        require(source["average"] == "15d" and source["approach"] == "from_below",
                "Frozen signal definition changed")
        require(source["confirmation"]["type"] == "bullish_candle", "Unsupported confirmation")
        specs[name] = SignalSpec(
            name=name,
            timeframe=source["signal_timeframe"],
            touch_zone_pct=float(source["touch_zone_pct"]),
            maximum_wait_minutes=int(source["confirmation"]["maximum_wait_minutes"]),
            avoid_strong_bearish=source["market_filter"]["type"] == "avoid_strong_bearish",
        )
    return specs, float(config["execution"]["slippage_bps_per_side"])


def reference_candidates(name: str, spec: SignalSpec) -> pd.DataFrame:
    path = (STAGE1 / "data/research/stage15/step5_exits_v1/SOLUSDT"
            / f"SOLUSDT_{spec.timeframe}_exit_candidates.parquet")
    columns = ["start_timestamp", "origin_regime", "status", "signal_candle_timestamp",
               "entry_timestamp", "confirmation_close", "average_type", "touch_zone", "policy",
               "approach"]
    frame = pd.read_parquet(path, columns=columns)
    frame = frame.loc[
        frame.average_type.eq("15d")
        & frame.touch_zone.eq(spec.touch_zone_pct)
        & frame.policy.eq("bullish_candle_30m")
        & frame.approach.eq("from_below")
    ].copy()
    if spec.avoid_strong_bearish:
        frame = frame.loc[~frame.origin_regime.eq("bearish") & frame.origin_regime.ne("missing")]
    frame["strategy"] = name
    return frame.sort_values("start_timestamp").reset_index(drop=True)


def validate_candidates(actual: pd.DataFrame, expected: pd.DataFrame, name: str) -> int:
    actual = actual.loc[actual.strategy.eq(name)].sort_values("start_timestamp").reset_index(drop=True)
    require(len(actual) == len(expected), f"{name}: candidate count mismatch")
    comparisons = [
        (actual.start_timestamp, expected.start_timestamp, "start timestamp"),
        (actual.origin_regime, expected.origin_regime, "origin regime"),
        (actual.status, expected.status, "status"),
        (actual.confirmation_timestamp, expected.signal_candle_timestamp, "confirmation timestamp"),
        (actual.entry_timestamp, expected.entry_timestamp, "entry timestamp"),
    ]
    for left, right, label in comparisons:
        pd.testing.assert_series_equal(left, right, check_names=False, check_dtype=False)
    confirmed = actual.status.eq("confirmed")
    require(np.allclose(
        actual.loc[confirmed, "confirmation_close"].astype(float),
        expected.loc[confirmed, "confirmation_close"].astype(float),
        rtol=0,
        atol=0,
    ), f"{name}: confirmation close mismatch")
    return len(actual)


def validate_fills(candidates: pd.DataFrame, fills: pd.DataFrame,
                   specs: dict[str, SignalSpec], slippage_bps: float) -> int:
    confirmed = candidates.loc[candidates.status.eq("confirmed"),
                               ["signal_id", "strategy", "start_timestamp", "entry_timestamp"]]
    actual = confirmed.merge(fills, on=["signal_id", "strategy"], validate="one_to_one")
    require(len(actual) == len(confirmed), "A confirmed signal was not filled")
    require((actual.entry_timestamp == actual.timestamp).all(), "Fill did not occur at entry boundary")
    require(np.allclose(actual.fill_price, actual.raw_open * (1 + slippage_bps / 10_000),
                        rtol=1e-14, atol=1e-14), "Entry slippage mismatch")

    checked = 0
    for name, spec in specs.items():
        path = (STAGE1 / "data/research/stage15_v2/step4_realistic_execution_v1/SOLUSDT"
                / f"SOLUSDT_{spec.timeframe}_execution_candidates.parquet")
        columns = ["start_timestamp", "entry_timestamp", "raw_entry_open", "realistic_entry_fill",
                   "average_type", "touch_zone", "policy", "approach", "origin_regime", "entered"]
        expected = pd.read_parquet(path, columns=columns)
        expected = expected.loc[
            expected.average_type.eq("15d")
            & expected.touch_zone.eq(spec.touch_zone_pct)
            & expected.policy.eq("bullish_candle_30m")
            & expected.approach.eq("from_below")
            & expected.entered
        ].copy()
        if spec.avoid_strong_bearish:
            expected = expected.loc[
                ~expected.origin_regime.eq("bearish") & expected.origin_regime.ne("missing")
            ]
        left = actual.loc[actual.strategy.eq(name)].sort_values("start_timestamp")
        right = expected.sort_values("start_timestamp")
        require(len(left) == len(right), f"{name}: fill reference count mismatch")
        pd.testing.assert_series_equal(
            left.entry_timestamp.reset_index(drop=True),
            right.entry_timestamp.reset_index(drop=True),
            check_names=False,
        )
        require(np.allclose(left.raw_open, right.raw_entry_open, rtol=0, atol=0),
                name + ": raw entry open mismatch")
        require(np.allclose(left.fill_price, right.realistic_entry_fill, rtol=1e-14, atol=1e-14),
                name + ": slipped entry fill mismatch")
        checked += len(left)
    return checked


def run() -> None:
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    specs, slippage_bps = load_config()
    raw_path = STAGE1 / "data/raw/SOLUSDT/SOLUSDT_1m.parquet"
    raw = pd.read_parquet(raw_path, columns=["open_time", "open", "high", "low", "close"])
    feeds = {}
    source_paths = [raw_path]
    for name, spec in specs.items():
        path = STAGE1 / f"data/processed/SOLUSDT/SOLUSDT_{spec.timeframe}_with_averages.parquet"
        source_paths.append(path)
        frame = pd.read_parquet(path, columns=SignalFeed.REQUIRED)
        feeds[name] = SignalFeed(frame, spec.timeframe)

    strategy = EntryReplayStrategy(feeds, specs, slippage_bps)
    started = perf_counter()
    engine_result = ChronologicalBacktester(raw).run(strategy)
    strategy.finalize()
    elapsed = perf_counter() - started
    candidates = strategy.candidate_frame()
    fills = strategy.fill_frame()

    candidate_checks = 0
    for name, spec in specs.items():
        candidate_checks += validate_candidates(candidates, reference_candidates(name, spec), name)
    fill_checks = validate_fills(candidates, fills, specs, slippage_bps)

    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    candidates.to_parquet(DATA / "entry_candidates.parquet", index=False)
    fills.to_parquet(DATA / "entry_fills.parquet", index=False)

    rows = []
    for name, generator in strategy.generators.items():
        current = candidates.loc[candidates.strategy.eq(name)]
        confirmed = current.loc[current.status.eq("confirmed")]
        rows.append({
            "strategy": name,
            "timeframe": specs[name].timeframe,
            "touch_episodes_seen": generator.episodes_seen,
            "from_below_episodes": generator.from_below_episodes,
            "market_rejections": generator.market_rejections,
            "eligible_candidates": len(current),
            "confirmed_signals": len(confirmed),
            "cancelled_signals": int(current.status.ne("confirmed").sum()),
            "fills": int(fills.strategy.eq(name).sum()),
            "earlier_fills": int((fills.strategy.eq(name) & fills.timestamp.lt("2025-09-01")).sum()),
            "later_fills": int((fills.strategy.eq(name) & fills.timestamp.ge("2025-09-01")).sum()),
            "mean_slippage_pct": ((fills.loc[fills.strategy.eq(name), "fill_price"]
                                     / fills.loc[fills.strategy.eq(name), "raw_open"] - 1) * 100).mean(),
        })
    summary = pd.DataFrame(rows)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    validation = {
        "step": "stage2_step3_entries",
        "status": "PASS",
        "candles_processed": engine_result.candle_count,
        "candidate_rows_matched_to_stage1_5": candidate_checks,
        "fills_matched_to_stage1_5": fill_checks,
        "entry_slippage_bps": slippage_bps,
        "elapsed_seconds": round(elapsed, 3),
        "source_sha256": {str(path.relative_to(STAGE1)): digest(path) for path in source_paths},
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    primary = summary.loc[summary.strategy.eq("primary")].iloc[0]
    control = summary.loc[summary.strategy.eq("control")].iloc[0]
    report = f"""# Stage 2 Step 3 — Entry Generation

## Result

The frozen entry logic was regenerated causally across all {engine_result.candle_count:,} raw SOLUSDT minutes. The primary produced **{primary.confirmed_signals:,}** fills ({primary.earlier_fills:,} earlier and {primary.later_fills:,} later). The control produced **{control.confirmed_signals:,}** fills ({control.earlier_fills:,} earlier and {control.later_fills:,} later). Every candidate status, confirmation time, entry time, raw opening price, and slipped fill matched the validated Stage 1.5 reference.

## Timing and price rules

Only a completed 3-minute or 5-minute candle can confirm an entry. A confirmed order waits for the raw 1-minute opening event at that same closing boundary. The simulated spot buy fills at `raw open × 1.0002`, applying 2 bps of adverse slippage. Fees remain separate for Step 5.

This step generates every qualifying entry independently. Signals that occur while a position is open will be removed only after exits determine the actual occupied interval.

## Validation

- {candidate_checks:,} candidate rows matched Stage 1.5.
- {fill_checks:,} entry fills matched Stage 1.5.
- Signal feeds were released only at their closing boundaries.
- The chronological engine processed each raw minute once.
- Stage 1 source files were read-only and are recorded by SHA-256.
"""
    (RESULTS / "REPORT.md").write_text(report)
    print(summary.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()
