"""Minute-close mark-to-market accounting for concurrent spot lots."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class _Lot:
    signal_id: str
    exit_timestamp: pd.Timestamp
    allocation_usd: float
    quantity: float
    exit_cash_usd: float
    realized_pnl_usd: float


def select_spot_lots(
    outcomes: pd.DataFrame,
    candles: pd.DataFrame,
    initial_equity_usd: float,
    equity_fraction_per_entry: float,
    maximum_positions: int,
) -> pd.DataFrame:
    """Select and size lots chronologically using equity known at each open."""
    required_outcomes = [
        "signal_id", "entry_timestamp", "exit_timestamp", "entry_cash_out_per_unit",
        "exit_cash_in_per_unit", "net_pnl_per_unit",
    ]
    required_candles = ["open_time", "open"]
    missing = [c for c in required_outcomes if c not in outcomes]
    if missing:
        raise ValueError(f"Missing outcome columns: {missing}")
    missing = [c for c in required_candles if c not in candles]
    if missing:
        raise ValueError(f"Missing candle columns: {missing}")
    if initial_equity_usd <= 0 or not 0 < equity_fraction_per_entry <= 1:
        raise ValueError("Initial equity and equity fraction must be positive")
    if maximum_positions < 1:
        raise ValueError("Maximum positions must be positive")

    ordered = outcomes.sort_values(["entry_timestamp", "signal_id"]).reset_index(drop=True)
    if ordered.signal_id.duplicated().any():
        raise ValueError("Duplicate signal ID")
    if (ordered.exit_timestamp <= ordered.entry_timestamp).any():
        raise ValueError("Exit must follow entry")
    opens = candles.set_index("open_time").open.astype(float)
    if not opens.index.is_unique:
        raise ValueError("Candle timestamps must be unique")

    cash = float(initial_equity_usd)
    active: list[_Lot] = []
    rows: list[dict] = []

    def close_due(timestamp: pd.Timestamp) -> None:
        nonlocal cash
        due = sorted(
            (lot for lot in active if lot.exit_timestamp <= timestamp),
            key=lambda lot: (lot.exit_timestamp, lot.signal_id),
        )
        for lot in due:
            active.remove(lot)
            cash += lot.exit_cash_usd

    for trade in ordered.itertuples(index=False):
        close_due(trade.entry_timestamp)
        if len(active) >= maximum_positions:
            continue
        if trade.entry_timestamp not in opens.index:
            raise ValueError(f"Entry candle absent: {trade.entry_timestamp}")
        current_open = float(opens.at[trade.entry_timestamp])
        equity_at_open = cash + sum(lot.quantity * current_open for lot in active)
        requested = equity_at_open * equity_fraction_per_entry
        allocation = min(requested, cash)
        if allocation <= 1e-12:
            continue
        quantity = allocation / float(trade.entry_cash_out_per_unit)
        exit_cash = quantity * float(trade.exit_cash_in_per_unit)
        pnl = quantity * float(trade.net_pnl_per_unit)
        lot = _Lot(
            signal_id=trade.signal_id,
            exit_timestamp=trade.exit_timestamp,
            allocation_usd=allocation,
            quantity=quantity,
            exit_cash_usd=exit_cash,
            realized_pnl_usd=pnl,
        )
        cash -= allocation
        active.append(lot)
        row = trade._asdict()
        row.update({
            "equity_at_entry_usd": equity_at_open,
            "allocation_usd": allocation,
            "allocation_pct_of_entry_equity": allocation / equity_at_open * 100,
            "quantity": quantity,
            "entry_fee_usd": quantity * float(trade.entry_fee_per_unit),
            "exit_fee_usd": quantity * float(trade.exit_fee_per_unit),
            "exit_cash_usd": exit_cash,
            "realized_pnl_usd": pnl,
        })
        rows.append(row)

    selected = pd.DataFrame(rows)
    if len(selected):
        selected = selected.sort_values(["entry_timestamp", "signal_id"]).reset_index(drop=True)
    return selected


def build_account_curve(
    candles: pd.DataFrame,
    selected_lots: pd.DataFrame,
    initial_equity_usd: float,
) -> pd.DataFrame:
    """Record the spot account after every candle close without forward prices."""
    required_candles = ["open_time", "close"]
    required_lots = [
        "signal_id", "entry_timestamp", "exit_timestamp", "allocation_usd", "quantity",
        "exit_cash_usd", "realized_pnl_usd",
    ]
    missing = [c for c in required_candles if c not in candles]
    if missing:
        raise ValueError(f"Missing candle columns: {missing}")
    missing = [c for c in required_lots if c not in selected_lots]
    if missing:
        raise ValueError(f"Missing selected-lot columns: {missing}")
    if initial_equity_usd <= 0:
        raise ValueError("Initial equity must be positive")

    frame = candles[required_candles].copy().reset_index(drop=True)
    times = pd.DatetimeIndex(frame.open_time)
    if times.tz is None or str(times.tz) != "UTC":
        raise ValueError("Candle timestamps must use UTC")
    if not times.is_monotonic_increasing or not times.is_unique:
        raise ValueError("Candle timestamps must be unique and increasing")
    if len(times) > 1 and not ((times[1:] - times[:-1]) == pd.Timedelta(minutes=1)).all():
        raise ValueError("Account tracking requires continuous one-minute candles")
    closes = frame.close.to_numpy(float)
    if not np.isfinite(closes).all() or not (closes > 0).all():
        raise ValueError("Close prices must be finite and positive")

    count = len(frame)
    cash_delta = np.zeros(count)
    quantity_delta = np.zeros(count)
    cost_delta = np.zeros(count)
    realized_delta = np.zeros(count)
    position_delta = np.zeros(count, dtype=np.int16)

    for lot in selected_lots.itertuples(index=False):
        entry_index = int(times.searchsorted(lot.entry_timestamp))
        if entry_index >= count or times[entry_index] != lot.entry_timestamp:
            raise ValueError(f"Entry is outside candle history: {lot.signal_id}")
        # An exit timestamp is a candle-close boundary, so its PnL belongs to
        # the candle beginning one minute earlier.
        exit_open_time = lot.exit_timestamp - pd.Timedelta(minutes=1)
        exit_index = int(times.searchsorted(exit_open_time))
        if exit_index < entry_index or exit_index >= count or times[exit_index] != exit_open_time:
            raise ValueError(f"Exit is outside candle history: {lot.signal_id}")

        cash_delta[entry_index] -= float(lot.allocation_usd)
        quantity_delta[entry_index] += float(lot.quantity)
        cost_delta[entry_index] += float(lot.allocation_usd)
        position_delta[entry_index] += 1

        cash_delta[exit_index] += float(lot.exit_cash_usd)
        quantity_delta[exit_index] -= float(lot.quantity)
        cost_delta[exit_index] -= float(lot.allocation_usd)
        realized_delta[exit_index] += float(lot.realized_pnl_usd)
        position_delta[exit_index] -= 1

    cash = initial_equity_usd + np.cumsum(cash_delta)
    quantity = np.cumsum(quantity_delta)
    cost_basis = np.cumsum(cost_delta)
    realized = np.cumsum(realized_delta)
    positions = np.cumsum(position_delta)
    quantity[np.abs(quantity) < 1e-12] = 0
    cost_basis[np.abs(cost_basis) < 1e-10] = 0
    open_value = quantity * closes
    unrealized = open_value - cost_basis
    equity = cash + open_value
    total_pnl = realized + unrealized
    peaks = np.maximum.accumulate(equity)
    drawdown = (equity / peaks - 1) * 100

    result = pd.DataFrame({
        "open_time": times,
        "timestamp": times + pd.Timedelta(minutes=1),
        "close_price": closes,
        "cash_usd": cash,
        "open_position_quantity": quantity,
        "open_position_cost_usd": cost_basis,
        "open_position_value_usd": open_value,
        "realized_pnl_usd": realized,
        "unrealized_pnl_usd": unrealized,
        "total_pnl_usd": total_pnl,
        "total_equity_usd": equity,
        "equity_peak_usd": peaks,
        "drawdown_pct": drawdown,
        "open_positions": positions,
    })
    if (cash < -1e-8).any() or (positions < 0).any():
        raise AssertionError("Account borrowed cash or has negative positions")
    if not np.allclose(equity - initial_equity_usd, total_pnl, atol=1e-8, rtol=1e-10):
        raise AssertionError("Account identity failed")
    return result

