"""Create auditable trade-ledger rows from selected, sized spot lots."""

from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = [
    "signal_id", "strategy", "entry_timestamp", "exit_timestamp", "duration_minutes",
    "exit_type", "raw_entry_open", "entry_fill", "raw_exit_price", "exit_fill",
    "entry_fee_per_unit", "exit_fee_per_unit", "entry_slippage_per_unit",
    "exit_slippage_per_unit", "entry_cash_out_per_unit", "exit_cash_in_per_unit",
    "gross_raw_return_pct", "net_return_pct", "equity_at_entry_usd", "allocation_usd",
    "allocation_pct_of_entry_equity", "quantity", "entry_fee_usd", "exit_fee_usd",
    "exit_cash_usd", "realized_pnl_usd",
]


def build_trade_records(selected_lots: pd.DataFrame) -> pd.DataFrame:
    """Return one reconciled record per completed trade."""
    missing = [column for column in REQUIRED_COLUMNS if column not in selected_lots]
    if missing:
        raise ValueError(f"Missing selected-lot columns: {missing}")
    lots = selected_lots.sort_values(["entry_timestamp", "signal_id"]).reset_index(drop=True)
    if lots.signal_id.duplicated().any():
        raise ValueError("Duplicate signal ID")
    if (lots.exit_timestamp <= lots.entry_timestamp).any():
        raise ValueError("Exit must follow entry")

    duration = (lots.exit_timestamp - lots.entry_timestamp).dt.total_seconds() / 60
    if not np.allclose(duration, lots.duration_minutes, rtol=0, atol=1e-12):
        raise ValueError("Stored duration does not match timestamps")

    entry_notional = lots.quantity * lots.entry_fill
    exit_notional = lots.quantity * lots.exit_fill
    total_fees = lots.entry_fee_usd + lots.exit_fee_usd
    entry_slippage = lots.quantity * lots.entry_slippage_per_unit
    exit_slippage = lots.quantity * lots.exit_slippage_per_unit
    gross_pnl = lots.quantity * (lots.raw_exit_price - lots.raw_entry_open)

    records = pd.DataFrame({
        "trade_id": [f"{strategy}-{index:04d}" for index, strategy in
                     enumerate(lots.strategy, start=1)],
        "signal_id": lots.signal_id,
        "strategy": lots.strategy,
        "entry_timestamp": lots.entry_timestamp,
        "exit_timestamp": lots.exit_timestamp,
        "duration_minutes": lots.duration_minutes.astype(int),
        "duration_hours": lots.duration_minutes / 60,
        "exit_reason": lots.exit_type,
        "outcome": np.where(lots.realized_pnl_usd > 0, "win", "loss"),
        "equity_at_entry_usd": lots.equity_at_entry_usd,
        "allocation_usd": lots.allocation_usd,
        "allocation_pct_of_equity": lots.allocation_pct_of_entry_equity,
        "size_sol": lots.quantity,
        "raw_entry_price": lots.raw_entry_open,
        "entry_fill_price": lots.entry_fill,
        "entry_notional_usd": entry_notional,
        "raw_exit_price": lots.raw_exit_price,
        "exit_fill_price": lots.exit_fill,
        "exit_notional_usd": exit_notional,
        "entry_fee_usd": lots.entry_fee_usd,
        "exit_fee_usd": lots.exit_fee_usd,
        "total_fees_usd": total_fees,
        "entry_slippage_usd": entry_slippage,
        "exit_slippage_usd": exit_slippage,
        "total_slippage_usd": entry_slippage + exit_slippage,
        "gross_pnl_before_costs_usd": gross_pnl,
        "gross_return_pct": lots.gross_raw_return_pct,
        "net_return_pct": lots.net_return_pct,
        "exit_cash_received_usd": lots.exit_cash_usd,
        "net_profit_usd": lots.realized_pnl_usd,
    })

    checks = [
        np.allclose(records.entry_notional_usd + records.entry_fee_usd,
                    records.allocation_usd, rtol=1e-11, atol=1e-11),
        np.allclose(records.exit_notional_usd - records.exit_fee_usd,
                    records.exit_cash_received_usd, rtol=1e-11, atol=1e-11),
        np.allclose(records.exit_cash_received_usd - records.allocation_usd,
                    records.net_profit_usd, rtol=1e-11, atol=1e-11),
        np.allclose(records.net_profit_usd / records.allocation_usd * 100,
                    records.net_return_pct, rtol=1e-11, atol=1e-11),
    ]
    if not all(checks):
        raise AssertionError("Trade cash flows do not reconcile")
    numeric = records.select_dtypes(include=[np.number])
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("Trade records contain non-finite numbers")
    return records


def trade_record_summary(records: pd.DataFrame) -> dict[str, float | int]:
    """Summarize the saved ledger without compounding overlapping trades."""
    wins = records.net_profit_usd > 0
    return {
        "trades": len(records),
        "wins": int(wins.sum()),
        "losses": int((~wins).sum()),
        "win_rate_pct": float(wins.mean() * 100),
        "total_allocated_usd": float(records.allocation_usd.sum()),
        "mean_trade_size_usd": float(records.allocation_usd.mean()),
        "total_entry_fees_usd": float(records.entry_fee_usd.sum()),
        "total_exit_fees_usd": float(records.exit_fee_usd.sum()),
        "total_fees_usd": float(records.total_fees_usd.sum()),
        "total_slippage_usd": float(records.total_slippage_usd.sum()),
        "net_profit_usd": float(records.net_profit_usd.sum()),
        "mean_net_profit_usd": float(records.net_profit_usd.mean()),
        "mean_duration_minutes": float(records.duration_minutes.mean()),
        "median_duration_minutes": float(records.duration_minutes.median()),
    }

