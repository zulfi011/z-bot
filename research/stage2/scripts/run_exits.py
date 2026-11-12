"""Run frozen primary and control exits through the chronological engine."""

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
from src.backtesting.exits import ExitReplayStrategy, ExitSpec  # noqa: E402


STAGE1 = ROOT.parent / "stage1"
RUN_ID = "step4_exits_v1"
DATA = ROOT / "data" / RUN_ID
RESULTS = ROOT / "results" / RUN_ID
CONFIG = ROOT / "config/strategies/sol_15d_touch_v1.yaml"
ENTRY_FILLS = ROOT / "data/step3_entries_v1/entry_fills.parquet"
REFERENCE_TRADES = ROOT / "data/trailing_activation_grid_v1/trades.parquet"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_specs() -> dict[str, ExitSpec]:
    config = yaml.safe_load(CONFIG.read_text())
    exits = config["exit"]
    slippage = float(config["execution"]["slippage_bps_per_side"])
    primary = exits["primary"]
    trail = primary["trailing_stop"]
    control = exits["control"]
    require(trail["enabled"] and not primary["fixed_profit_target"]["enabled"],
            "Frozen primary trailing selection changed")
    require(not control["trailing_stop"]["enabled"], "Frozen control exit changed")
    return {
        "primary": ExitSpec(
            strategy="primary",
            mode=primary["mode"],
            stop_pct=float(primary["protective_stop_pct_from_entry_fill"]),
            maximum_hold_minutes=int(exits["maximum_hold_minutes"]),
            exit_slippage_bps=slippage,
            trail_activation_pct=float(trail["activation_pct_from_entry_fill"]),
            trail_giveback_pct=float(trail["giveback_of_open_profit_pct"]),
        ),
        "control": ExitSpec(
            strategy="control",
            mode=control["mode"],
            stop_pct=float(control["protective_stop_pct_from_entry_fill"]),
            maximum_hold_minutes=int(exits["maximum_hold_minutes"]),
            exit_slippage_bps=slippage,
            target_pct=float(control["profit_target_pct_from_entry_fill"]),
        ),
    }


def validate_nonoverlap(completed: pd.DataFrame, incomplete: pd.DataFrame) -> int:
    checks = 0
    for strategy, frame in completed.groupby("strategy"):
        ordered = frame.sort_values("entry_timestamp")
        if len(ordered) > 1:
            require(bool((ordered.entry_timestamp.iloc[1:].reset_index(drop=True)
                          >= ordered.exit_timestamp.iloc[:-1].reset_index(drop=True)).all()),
                    f"{strategy}: overlapping completed positions")
            checks += len(ordered) - 1
        pending = incomplete.loc[incomplete.strategy.eq(strategy)]
        if len(pending):
            require(len(pending) == 1, f"{strategy}: multiple incomplete positions")
            require(pending.entry_timestamp.iloc[0] >= ordered.exit_timestamp.iloc[-1],
                    f"{strategy}: incomplete position overlaps a completed trade")
            checks += 1
    return checks


def validate_reference(completed: pd.DataFrame) -> int:
    reference = pd.read_parquet(REFERENCE_TRADES)
    expected_parts = []
    for strategy, variant in [("primary", "trail_a4_g10"), ("control", "fixed_4")]:
        part = reference.loc[
            reference.strategy.eq(strategy) & reference.variant.eq(variant)
        ].copy()
        expected_parts.append(part)
    expected = pd.concat(expected_parts, ignore_index=True)
    left = completed.sort_values(["strategy", "entry_timestamp"]).reset_index(drop=True)
    right = expected.sort_values(["strategy", "entry_timestamp"]).reset_index(drop=True)
    require(len(left) == len(right), "Completed trade count differs from independent analysis")
    pd.testing.assert_series_equal(left.strategy, right.strategy, check_names=False)
    pd.testing.assert_series_equal(left.entry_timestamp, right.entry_timestamp, check_names=False)
    pd.testing.assert_series_equal(left.exit_type, right.exit_type, check_names=False)
    require(np.allclose(left.entry_fill, right.entry_fill, rtol=0, atol=0),
            "Entry fill reference mismatch")
    require(np.allclose(left.raw_exit_price, right.raw_exit, rtol=1e-13, atol=1e-13),
            "Raw exit reference mismatch")
    require(np.allclose(left.exit_fill, right.exit_fill, rtol=1e-13, atol=1e-13),
            "Exit fill reference mismatch")
    require(np.array_equal(left.duration_minutes, right.duration_minutes),
            "Exit duration reference mismatch")
    expected_return = (right.exit_fill / right.entry_fill - 1) * 100
    require(np.allclose(left.return_after_slippage_pct, expected_return, rtol=1e-13, atol=1e-13),
            "Pre-fee return reference mismatch")
    return len(left)


def summarize(completed: pd.DataFrame, ignored: pd.DataFrame,
              incomplete: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy, frame in completed.groupby("strategy", sort=True):
        exits = frame.exit_type.value_counts()
        rows.append({
            "strategy": strategy,
            "completed_trades": len(frame),
            "ignored_signals_while_open": int(ignored.strategy.eq(strategy).sum()),
            "incomplete_at_data_end": int(incomplete.strategy.eq(strategy).sum()),
            "profit_target_exits": int(exits.get("profit_target", 0)),
            "trailing_stop_exits": int(exits.get("trailing_stop", 0)),
            "hard_stop_exits": int(exits.get("protective_stop", 0)),
            "ambiguous_stop_exits": int(exits.get("ambiguous_stop", 0)),
            "time_exits": int(exits.get("time", 0)),
            "trailing_activated_trades": int(frame.trailing_activated.sum()),
            "median_duration_minutes": frame.duration_minutes.median(),
            "mean_return_after_slippage_pct": frame.return_after_slippage_pct.mean(),
        })
    return pd.DataFrame(rows)


def run() -> None:
    require(not DATA.exists() and not RESULTS.exists(), "Run already exists; refusing overwrite")
    specs = load_specs()
    fills = pd.read_parquet(ENTRY_FILLS)
    raw_path = STAGE1 / "data/raw/SOLUSDT/SOLUSDT_1m.parquet"
    raw = pd.read_parquet(raw_path, columns=["open_time", "open", "high", "low", "close"])
    replay = ExitReplayStrategy(fills, specs)
    started = perf_counter()
    engine_result = ChronologicalBacktester(raw).run(replay)
    replay.finalize(engine_result.ended_at)
    elapsed = perf_counter() - started

    completed = replay.completed_frame()
    ignored = replay.ignored_frame()
    incomplete = replay.incomplete_frame()
    require(len(completed) + len(ignored) + len(incomplete) == len(fills),
            "Entry signals were lost or counted twice")
    overlap_checks = validate_nonoverlap(completed, incomplete)
    reference_checks = validate_reference(completed)
    require(len(completed.loc[completed.strategy.eq("primary")]) == 82,
            "Unexpected primary completed-trade count")
    require(len(completed.loc[completed.strategy.eq("control")]) == 117,
            "Unexpected control completed-trade count")
    require(len(incomplete) == 1 and incomplete.strategy.iloc[0] == "control",
            "Unexpected incomplete position")

    DATA.mkdir(parents=True)
    RESULTS.mkdir(parents=True)
    completed.to_parquet(DATA / "completed_trades.parquet", index=False)
    ignored.to_parquet(DATA / "ignored_entries.parquet", index=False)
    incomplete.to_parquet(DATA / "incomplete_positions.parquet", index=False)
    summary = summarize(completed, ignored, incomplete)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    validation = {
        "step": "stage2_step4_exits",
        "status": "PASS",
        "candles_processed": engine_result.candle_count,
        "input_entry_fills": len(fills),
        "completed_trades": len(completed),
        "ignored_entries": len(ignored),
        "incomplete_positions": len(incomplete),
        "nonoverlap_checks": overlap_checks,
        "trades_matched_to_independent_exit_analysis": reference_checks,
        "elapsed_seconds": round(elapsed, 3),
        "source_sha256": {
            "entry_fills": sha256(ENTRY_FILLS),
            "raw_1m": sha256(raw_path),
            "reference_trades": sha256(REFERENCE_TRADES),
        },
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    primary = summary.loc[summary.strategy.eq("primary")].iloc[0]
    control = summary.loc[summary.strategy.eq("control")].iloc[0]
    report = f"""# Stage 2 Step 4 — Exit Execution

## Result

The chronological engine managed each strategy as a separate one-position spot account. It completed **{primary.completed_trades:,} primary trades** and **{control.completed_trades:,} control trades**. It ignored {primary.ignored_signals_while_open:,} primary and {control.ignored_signals_while_open:,} control signals received while their positions were open. One final control entry lacked the complete 24-hour path and remains explicitly incomplete.

## Primary exits

The primary keeps its −4% hard stop. Reaching +4% activates the 10% giveback-of-open-profit trail, which begins on the following raw minute using the previously known peak. Results: **{primary.trailing_stop_exits:,} trailing exits**, **{primary.hard_stop_exits + primary.ambiguous_stop_exits:,} hard/ambiguous stops**, and **{primary.time_exits:,} 24-hour exits**.

## Control exits

The control retains its fixed +4% profit target and −4% hard stop. Results: **{control.profit_target_exits:,} targets**, **{control.hard_stop_exits + control.ambiguous_stop_exits:,} hard/ambiguous stops**, and **{control.time_exits:,} 24-hour exits**.

## Execution rules

Targets, stops, and trailing levels are calculated from the slipped entry fill. Same-minute conflicts resolve to the hard stop. Stop and trail gaps use the worse of the level or candle open; favorable target gaps use the candle open. Exit fills include 2 bps adverse sell slippage. Trading fees are intentionally deferred to Step 5.

All {reference_checks:,} completed trades matched the independent Stage 1.5/Stage 2 trailing analysis for entry, exit type, duration, raw exit, and slipped exit fill.
"""
    (RESULTS / "REPORT.md").write_text(report)
    print(summary.to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()

