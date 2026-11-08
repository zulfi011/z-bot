import numpy as np
import pandas as pd
import pytest

from src.backtesting.trade_records import build_trade_records, trade_record_summary


START = pd.Timestamp("2026-01-01", tz="UTC")


def selected_lot():
    quantity = 2.0
    entry_fill = 10.0
    exit_fill = 11.0
    entry_fee = 0.02
    exit_fee = 0.022
    allocation = quantity * entry_fill + entry_fee
    exit_cash = quantity * exit_fill - exit_fee
    return pd.DataFrame([{
        "signal_id": "signal-a", "strategy": "primary",
        "entry_timestamp": START, "exit_timestamp": START + pd.Timedelta(minutes=60),
        "duration_minutes": 60, "exit_type": "trailing_stop",
        "raw_entry_open": 9.98, "entry_fill": entry_fill,
        "raw_exit_price": 11.02, "exit_fill": exit_fill,
        "entry_fee_per_unit": entry_fee / quantity,
        "exit_fee_per_unit": exit_fee / quantity,
        "entry_slippage_per_unit": 0.02, "exit_slippage_per_unit": 0.02,
        "entry_cash_out_per_unit": allocation / quantity,
        "exit_cash_in_per_unit": exit_cash / quantity,
        "gross_raw_return_pct": (11.02 / 9.98 - 1) * 100,
        "net_return_pct": (exit_cash / allocation - 1) * 100,
        "equity_at_entry_usd": 100, "allocation_usd": allocation,
        "allocation_pct_of_entry_equity": allocation,
        "quantity": quantity, "entry_fee_usd": entry_fee,
        "exit_fee_usd": exit_fee, "exit_cash_usd": exit_cash,
        "realized_pnl_usd": exit_cash - allocation,
    }])


def test_trade_record_contains_and_reconciles_cash_flows():
    records = build_trade_records(selected_lot())
    row = records.iloc[0]
    assert row.exit_reason == "trailing_stop"
    assert row.duration_hours == 1
    assert row.size_sol == 2
    assert np.isclose(row.total_fees_usd, 0.042)
    assert np.isclose(row.net_profit_usd, row.exit_cash_received_usd - row.allocation_usd)
    summary = trade_record_summary(records)
    assert summary["trades"] == 1 and summary["wins"] == 1


def test_trade_record_rejects_duration_that_disagrees_with_timestamps():
    lot = selected_lot()
    lot.loc[0, "duration_minutes"] = 59
    with pytest.raises(ValueError, match="duration"):
        build_trade_records(lot)

