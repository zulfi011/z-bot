"""Cash-constrained concurrent spot-lot portfolio simulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .position_sizing import SizingSpec, allocation_for_trade


@dataclass
class _OpenLot:
    signal_id: str
    exit_timestamp: pd.Timestamp
    allocation_usd: float
    net_return_pct: float


def simulate_concurrent_positions(
    trades: pd.DataFrame,
    sizing: SizingSpec,
    initial_equity: float,
    stop_loss_fraction: float,
    maximum_positions: int,
) -> pd.DataFrame:
    """Replay independent spot lots while enforcing slots and available cash."""
    required = ["signal_id", "strategy", "entry_timestamp", "exit_timestamp", "net_return_pct"]
    missing = [column for column in required if column not in trades]
    if missing:
        raise ValueError(f"Missing concurrent-position columns: {missing}")
    if maximum_positions < 1 or initial_equity <= 0:
        raise ValueError("Position limit and initial equity must be positive")
    ordered = trades.sort_values(["entry_timestamp", "signal_id"]).reset_index(drop=True)
    if ordered.signal_id.duplicated().any():
        raise ValueError("Duplicate signal ID")
    if (ordered.exit_timestamp <= ordered.entry_timestamp).any():
        raise ValueError("Exit must occur after entry")

    cash = float(initial_equity)
    peak = cash
    active: list[_OpenLot] = []
    events: list[dict] = []

    def snapshot(timestamp, event_type, signal_id, allocation=0.0, pnl=0.0,
                 reason=None, requested=0.0):
        nonlocal peak
        committed = sum(lot.allocation_usd for lot in active)
        equity = cash + committed
        peak = max(peak, equity)
        events.append({
            "timestamp": timestamp,
            "event_type": event_type,
            "signal_id": signal_id,
            "reason": reason,
            "requested_allocation_usd": requested,
            "allocation_usd": allocation,
            "net_pnl_usd": pnl,
            "cash_usd": cash,
            "committed_capital_usd": committed,
            "book_equity_usd": equity,
            "book_equity_peak_usd": peak,
            "book_drawdown_pct": (equity / peak - 1) * 100,
            "open_positions": len(active),
            "deployment_pct": committed / equity * 100 if equity > 0 else np.nan,
            "planned_open_risk_pct": committed * stop_loss_fraction / equity * 100
            if equity > 0 else np.nan,
        })

    def close_due(until: pd.Timestamp):
        nonlocal cash, active
        due = sorted((lot for lot in active if lot.exit_timestamp <= until),
                     key=lambda lot: (lot.exit_timestamp, lot.signal_id))
        for lot in due:
            active.remove(lot)
            proceeds = lot.allocation_usd * (1 + lot.net_return_pct / 100)
            pnl = proceeds - lot.allocation_usd
            cash += proceeds
            snapshot(lot.exit_timestamp, "exit", lot.signal_id,
                     allocation=lot.allocation_usd, pnl=pnl)

    for trade in ordered.itertuples(index=False):
        close_due(trade.entry_timestamp)
        committed = sum(lot.allocation_usd for lot in active)
        equity = cash + committed
        if len(active) >= maximum_positions:
            snapshot(trade.entry_timestamp, "skip", trade.signal_id,
                     reason="position_limit")
            continue
        requested = allocation_for_trade(equity, sizing, stop_loss_fraction)
        allocation = min(requested, cash)
        if allocation <= 1e-12:
            snapshot(trade.entry_timestamp, "skip", trade.signal_id,
                     reason="insufficient_cash", requested=requested)
            continue
        cash -= allocation
        active.append(_OpenLot(
            signal_id=trade.signal_id,
            exit_timestamp=trade.exit_timestamp,
            allocation_usd=allocation,
            net_return_pct=float(trade.net_return_pct),
        ))
        snapshot(trade.entry_timestamp, "entry", trade.signal_id,
                 allocation=allocation, requested=requested,
                 reason="partial_cash_fill" if allocation < requested - 1e-12 else None)

    if len(ordered):
        close_due(max(lot.exit_timestamp for lot in active) if active else ordered.exit_timestamp.max())
    if active:
        raise AssertionError("Not every opened lot closed")
    result = pd.DataFrame(events)
    if len(result):
        if (result.cash_usd < -1e-10).any() or (result.committed_capital_usd < -1e-10).any():
            raise AssertionError("Portfolio borrowed cash or held negative capital")
        if (result.deployment_pct > 100 + 1e-10).any():
            raise AssertionError("Portfolio deployment exceeded 100%")
    return result


def concurrent_metrics(events: pd.DataFrame, initial_equity: float) -> dict[str, float | int]:
    entries = events.loc[events.event_type.eq("entry")]
    exits = events.loc[events.event_type.eq("exit")]
    skips = events.loc[events.event_type.eq("skip")]
    final_equity = events.book_equity_usd.iloc[-1]
    return {
        "opened_trades": len(entries),
        "completed_trades": len(exits),
        "skipped_position_limit": int(skips.reason.eq("position_limit").sum()),
        "skipped_no_cash": int(skips.reason.eq("insufficient_cash").sum()),
        "partial_cash_fills": int(entries.reason.eq("partial_cash_fill").sum()),
        "max_positions_observed": int(events.open_positions.max()),
        "mean_allocation_usd": entries.allocation_usd.mean(),
        "mean_allocation_pct_of_initial": entries.allocation_usd.mean() / initial_equity * 100,
        "max_deployment_pct": events.deployment_pct.max(),
        "max_planned_open_risk_pct": events.planned_open_risk_pct.max(),
        "final_equity_usd": final_equity,
        "total_pnl_usd": final_equity - initial_equity,
        "total_return_pct": (final_equity / initial_equity - 1) * 100,
        "max_book_drawdown_pct": events.book_drawdown_pct.min(),
    }

