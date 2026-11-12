"""Independently audit causality, exits, costs, overlap, and balances."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtesting.account import select_spot_lots  # noqa: E402
from src.backtesting.engine import (  # noqa: E402
    Candle, ChronologicalBacktester, CloseEvent, FutureDataAccessError,
)
from src.backtesting.exits import ExitSpec, Position, evaluate_exit  # noqa: E402


RUN_ID = "step10_strict_validation_v1"
RESULTS = ROOT / "results" / RUN_ID
RAW = ROOT.parent / "foundations/data/raw/SOLUSDT/SOLUSDT_1m.parquet"
OUTCOMES = ROOT / "data/step6b_concurrent_positions_v1/all_signal_outcomes.parquet"
STEP7 = ROOT / "data/step7_account_tracking_v1"
STEP8 = ROOT / "data/step8_trade_records_v1"
FEE_RATE = 10 / 10_000
SLIPPAGE_RATE = 2 / 10_000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def audit_lookahead(raw: pd.DataFrame) -> int:
    class Probe:
        def __init__(self):
            self.blocked = 0

        def on_open(self, event, history):
            try:
                history.at(event.timestamp)
            except FutureDataAccessError:
                self.blocked += 1

        def on_close(self, event, history):
            require(history.at(event.candle.open_time) == event.candle,
                    "Closed candle was unavailable at close")
            try:
                history.at(event.timestamp)
            except FutureDataAccessError:
                self.blocked += 1

    probe = Probe()
    ChronologicalBacktester(raw.iloc[:10].copy()).run(probe)
    require(probe.blocked == 20, "Future candle access was not blocked at every phase")
    return probe.blocked


def independent_exit_replay(records: pd.DataFrame, raw: pd.DataFrame) -> int:
    specs = {
        "primary": ExitSpec("primary", "trailing_after_activation", 4, 1440, 2,
                            trail_activation_pct=4, trail_giveback_pct=10),
        "control": ExitSpec("control", "fixed_profit_target", 4, 1440, 2,
                            target_pct=4),
    }
    times = pd.DatetimeIndex(raw.open_time)
    checked = 0
    for trade in records.itertuples(index=False):
        start = int(times.searchsorted(trade.entry_timestamp))
        require(start < len(raw) and times[start] == trade.entry_timestamp,
                f"Entry candle missing for {trade.trade_id}")
        position = Position(
            trade.signal_id, trade.strategy, trade.entry_timestamp,
            float(trade.raw_entry_price), float(trade.entry_fill_price),
        )
        completed = None
        for offset, row in enumerate(raw.iloc[start:start + 1440].itertuples(index=False)):
            candle = Candle(row.open_time, float(row.open), float(row.high),
                            float(row.low), float(row.close))
            event = CloseEvent(start + offset, row.open_time + pd.Timedelta(minutes=1), candle)
            completed = evaluate_exit(position, event, specs[trade.strategy])
            if completed is not None:
                break
        require(completed is not None, f"No exit reconstructed for {trade.trade_id}")
        require(completed.exit_timestamp == trade.exit_timestamp,
                f"Exit time mismatch for {trade.trade_id}")
        require(completed.exit_type == trade.exit_reason,
                f"Exit reason mismatch for {trade.trade_id}")
        require(completed.duration_minutes == trade.duration_minutes,
                f"Duration mismatch for {trade.trade_id}")
        require(np.isclose(completed.raw_exit_price, trade.raw_exit_price,
                           rtol=1e-12, atol=1e-12),
                f"Raw exit mismatch for {trade.trade_id}")
        require(np.isclose(completed.exit_fill, trade.exit_fill_price,
                           rtol=1e-12, atol=1e-12),
                f"Exit fill mismatch for {trade.trade_id}")
        checked += 1
    return checked


def audit_same_candle_policy() -> int:
    timestamp = pd.Timestamp("2026-01-01", tz="UTC")
    ambiguous = CloseEvent(
        0, timestamp + pd.Timedelta(minutes=1), Candle(timestamp, 100, 105, 95, 100)
    )
    primary = ExitSpec("primary", "trailing_after_activation", 4, 1440, 2,
                       trail_activation_pct=4, trail_giveback_pct=10)
    control = ExitSpec("control", "fixed_profit_target", 4, 1440, 2, target_pct=4)
    for strategy, spec in [("primary", primary), ("control", control)]:
        result = evaluate_exit(Position("probe", strategy, timestamp, 100, 100),
                               ambiguous, spec)
        require(result is not None and result.exit_type == "ambiguous_stop",
                "Same-candle stop did not win")
        require(result.raw_exit_price == 96, "Ambiguous exit did not use hard stop")

    activation = CloseEvent(
        0, timestamp + pd.Timedelta(minutes=1), Candle(timestamp, 100, 105, 100, 104)
    )
    position = Position("probe", "primary", timestamp, 100, 100)
    require(evaluate_exit(position, activation, primary) is None,
            "Activation candle incorrectly triggered trailing exit")
    require(position.trailing_active, "Trailing state failed to activate")
    return 3


def audit_overlap_and_selection(
    outcomes: pd.DataFrame, raw: pd.DataFrame, records: pd.DataFrame,
) -> tuple[int, int]:
    max_observed = 0
    selection_matches = 0
    for strategy in ["primary", "control"]:
        expected = select_spot_lots(
            outcomes.loc[outcomes.strategy.eq(strategy)], raw, 100, 0.25, 2
        )
        actual = records.loc[records.strategy.eq(strategy)]
        require(expected.signal_id.tolist() == actual.signal_id.tolist(),
                f"Selected signals changed for {strategy}")
        require(np.allclose(expected.allocation_usd, actual.allocation_usd,
                            rtol=1e-12, atol=1e-12),
                f"Allocations changed for {strategy}")
        selection_matches += len(actual)

        events = []
        for trade in actual.itertuples(index=False):
            events.append((trade.entry_timestamp, 1, trade.trade_id))
            events.append((trade.exit_timestamp, 0, trade.trade_id))
        open_count = 0
        for _, kind, _ in sorted(events):  # exit kind 0 precedes entry kind 1
            open_count += 1 if kind == 1 else -1
            require(0 <= open_count <= 2, f"Position overlap limit failed for {strategy}")
            max_observed = max(max_observed, open_count)
        require(open_count == 0, f"Unclosed position in {strategy}")
    return selection_matches, max_observed


def audit_costs(records: pd.DataFrame) -> int:
    require(np.allclose(records.entry_fill_price,
                        records.raw_entry_price * (1 + SLIPPAGE_RATE)),
            "Entry slippage mismatch")
    require(np.allclose(records.exit_fill_price,
                        records.raw_exit_price * (1 - SLIPPAGE_RATE)),
            "Exit slippage mismatch")
    entry_notional = records.size_sol * records.entry_fill_price
    exit_notional = records.size_sol * records.exit_fill_price
    entry_fee = entry_notional * FEE_RATE
    exit_fee = exit_notional * FEE_RATE
    require(np.allclose(entry_fee, records.entry_fee_usd), "Entry fee mismatch")
    require(np.allclose(exit_fee, records.exit_fee_usd), "Exit fee mismatch")
    require(np.allclose(entry_notional + entry_fee, records.allocation_usd),
            "Entry cash mismatch")
    require(np.allclose(exit_notional - exit_fee, records.exit_cash_received_usd),
            "Exit cash mismatch")
    require(np.allclose(records.exit_cash_received_usd - records.allocation_usd,
                        records.net_profit_usd), "Net PnL mismatch")
    return len(records)


def audit_balances(records: pd.DataFrame) -> tuple[int, float]:
    rows = 0
    max_error = 0.0
    for strategy in ["primary", "control"]:
        curve = pd.read_parquet(STEP7 / f"{strategy}_account_curve_1m.parquet")
        identity_a = abs(curve.cash_usd + curve.open_position_value_usd - curve.total_equity_usd)
        identity_b = abs(100 + curve.realized_pnl_usd + curve.unrealized_pnl_usd
                         - curve.total_equity_usd)
        max_error = max(max_error, float(identity_a.max()), float(identity_b.max()))
        require(max_error < 1e-9, f"Account identity failed for {strategy}")
        require(curve.cash_usd.min() >= -1e-10, f"Negative cash for {strategy}")
        require(curve.open_positions.max() <= 2, f"Too many positions for {strategy}")
        require(curve.open_positions.iloc[-1] == 0, f"Open final position for {strategy}")
        pnl = records.loc[records.strategy.eq(strategy), "net_profit_usd"].sum()
        require(np.isclose(curve.total_equity_usd.iloc[-1], 100 + pnl,
                           rtol=1e-12, atol=1e-12),
                f"Final PnL mismatch for {strategy}")
        rows += len(curve)
    return rows, max_error


def run() -> None:
    if RESULTS.exists():
        raise ValueError("Run already exists; refusing overwrite")
    raw = pd.read_parquet(RAW, columns=["open_time", "open", "high", "low", "close"])
    outcomes = pd.read_parquet(OUTCOMES)
    records = pd.read_parquet(STEP8 / "all_trades.parquet")
    require(len(raw) == 1_006_560, "Raw candle count changed")
    require(len(records) == 361, "Trade record count changed")

    checks = []
    blocked = audit_lookahead(raw)
    checks.append(("lookahead_prevention", "PASS", blocked, "future access probes blocked"))
    exits = independent_exit_replay(records, raw)
    checks.append(("independent_exit_replay", "PASS", exits, "trade exits matched"))
    policies = audit_same_candle_policy()
    checks.append(("same_candle_exit_policy", "PASS", policies, "conservative cases passed"))
    selections, max_positions = audit_overlap_and_selection(outcomes, raw, records)
    checks.append(("overlap_and_selection", "PASS", selections,
                   f"trades matched; maximum positions {max_positions}"))
    costs = audit_costs(records)
    checks.append(("cost_calculations", "PASS", costs, "trade cash flows matched"))
    account_rows, max_error = audit_balances(records)
    checks.append(("balance_reconciliation", "PASS", account_rows,
                   f"account rows; max error {max_error:.3e}"))

    RESULTS.mkdir(parents=True)
    pd.DataFrame(checks, columns=["check", "status", "observations", "detail"]).to_csv(
        RESULTS / "audit_checks.csv", index=False
    )
    validation = {
        "step": "stage2_step10_strict_validation",
        "status": "PASS",
        "lookahead_probes_blocked": blocked,
        "independently_replayed_exits": exits,
        "same_candle_policy_cases": policies,
        "selection_and_overlap_records_checked": selections,
        "maximum_positions_observed": max_positions,
        "costed_trades_recalculated": costs,
        "account_rows_reconciled": account_rows,
        "maximum_balance_error_usd": max_error,
        "raw_source_sha256": sha256(RAW),
        "outcomes_source_sha256": sha256(OUTCOMES),
        "trades_source_sha256": sha256(STEP8 / "all_trades.parquet"),
    }
    (RESULTS / "validation.json").write_text(json.dumps(validation, indent=2) + "\n")
    print(pd.DataFrame(checks, columns=["check", "status", "observations", "detail"])
          .to_string(index=False))
    print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    run()

