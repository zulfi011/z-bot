"""Run the phase-aware engine across the complete validated SOL minute history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.engine import ChronologicalBacktester, FutureDataAccessError  # noqa: E402


SOURCE = ROOT.parent / "stage1_research/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
OUTPUT = ROOT / "results/step2_chronological_engine_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class FullHistoryAudit:
    def __init__(self):
        self.expected_open = 0
        self.expected_close = 0
        self.lookahead_blocks = 0
        self.boundary_checks = 0

    def on_open(self, event, history):
        if event.index != self.expected_open or history.closed_count != event.index:
            raise AssertionError("Open callback is out of chronological order")
        if event.index == 0:
            try:
                history.at(event.timestamp)
            except FutureDataAccessError:
                self.lookahead_blocks += 1
            else:
                raise AssertionError("Current unclosed candle leaked at open")
        if event.index % 100_000 == 0 and event.index:
            if history.latest.open_time >= event.timestamp:
                raise AssertionError("Open history contains current/future data")
            self.boundary_checks += 1
        self.expected_open += 1

    def on_close(self, event, history):
        if event.index != self.expected_close or history.closed_count != event.index + 1:
            raise AssertionError("Close callback is out of chronological order")
        if event.index == 0:
            if history.at(event.candle.open_time) != event.candle:
                raise AssertionError("Closed candle unavailable at close")
            try:
                history.at(event.timestamp)
            except FutureDataAccessError:
                self.lookahead_blocks += 1
            else:
                raise AssertionError("Next candle leaked at prior close")
        if event.index % 100_000 == 0:
            if history.latest != event.candle:
                raise AssertionError("Latest closed candle mismatch")
            self.boundary_checks += 1
        self.expected_close += 1


def run() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    candles = pd.read_parquet(SOURCE, columns=["open_time", "open", "high", "low", "close"])
    strategy = FullHistoryAudit()
    started = perf_counter()
    result = ChronologicalBacktester(candles, frequency="1min").run(strategy)
    elapsed = perf_counter() - started
    if result.candle_count != len(candles):
        raise AssertionError("Not every candle was processed")
    if result.open_callbacks != result.close_callbacks or result.open_callbacks != len(candles):
        raise AssertionError("Callback counts do not match candle count")
    if strategy.lookahead_blocks != 2:
        raise AssertionError("Look-ahead probes were not blocked")

    validation = {
        "step": "stage2_step2_chronological_engine",
        "status": "PASS",
        "source": str(SOURCE.relative_to(ROOT.parent)),
        "source_sha256": sha256(SOURCE),
        "candles_processed": result.candle_count,
        "open_callbacks": result.open_callbacks,
        "close_callbacks": result.close_callbacks,
        "first_open_utc": str(result.started_at),
        "last_close_utc": str(result.ended_at),
        "lookahead_probes_blocked": strategy.lookahead_blocks,
        "sampled_history_boundary_checks": strategy.boundary_checks,
        "elapsed_seconds": round(elapsed, 3),
    }
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    report = f"""# Stage 2 Step 2 — Chronological Engine Validation

The engine processed all **{result.candle_count:,}** validated SOLUSDT 1-minute candles from **{result.started_at}** through the final close at **{result.ended_at}**. Each candle produced one open callback and one close callback in order.

At candle open, strategies receive only the opening price and previously closed history. The full current candle becomes available at its close. Both deliberate future-data requests were rejected, and {strategy.boundary_checks:,} sampled history-boundary checks passed. Input validation also rejects missing columns, invalid OHLC values, duplicate timestamps, unordered timestamps, and candle gaps.

This step supplies the causal event loop and immutable candle/history views. Trading entries, exits, costs, position sizing, and account balances attach through the strategy callbacks in the following Stage 2 steps.
"""
    (OUTPUT / "REPORT.md").write_text(report)
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()

