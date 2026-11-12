import numpy as np
import pandas as pd
import pytest

from src.backtesting.position_sizing import (
    SizingSpec,
    allocation_for_trade,
    planned_stop_loss_fraction,
    simulate_position_sizing,
)


def trades(returns=(10.0, -10.0)):
    rows = []
    start = pd.Timestamp("2026-01-01", tz="UTC")
    for index, value in enumerate(returns):
        entry = start + pd.Timedelta(days=index)
        entry_cash = 100.0
        exit_cash = entry_cash * (1 + value / 100)
        rows.append({
            "signal_id": str(index), "strategy": "primary",
            "entry_timestamp": entry, "exit_timestamp": entry + pd.Timedelta(hours=1),
            "entry_cash_out_per_unit": entry_cash,
            "exit_cash_in_per_unit": exit_cash,
            "net_pnl_per_unit": exit_cash - entry_cash,
            "net_return_pct": value,
            "entry_fee_per_unit": 0.1, "exit_fee_per_unit": 0.1,
            "total_slippage_per_unit": 0.04,
        })
    return pd.DataFrame(rows)


def test_fixed_capital_uses_same_dollars_until_cash_cap():
    result = simulate_position_sizing(
        trades((-60.0, -60.0)), SizingSpec("fixed_50", "fixed_capital", 50), 100, 0.04
    )
    assert result.allocation_usd.tolist() == [50, 50]
    assert np.isclose(result.equity_after_usd.iloc[-1], 40)


def test_equity_fraction_compounds_position_size():
    result = simulate_position_sizing(
        trades((10.0, 10.0)), SizingSpec("equity_50", "equity_fraction", 0.5), 100, 0.04
    )
    assert np.allclose(result.allocation_usd, [50, 52.5])
    assert np.isclose(result.equity_after_usd.iloc[-1], 110.25)


def test_risk_sizing_uses_stop_loss_and_respects_spot_cap():
    one_percent = SizingSpec("risk_1", "risk_fraction", 0.01)
    assert np.isclose(allocation_for_trade(100, one_percent, 0.04), 25)
    large_risk = SizingSpec("risk_10", "risk_fraction", 0.10)
    assert allocation_for_trade(100, large_risk, 0.04) == 100


def test_planned_stop_includes_exit_slippage_and_both_fees():
    loss = planned_stop_loss_fraction(4, 10, 2)
    expected = 1 - (0.96 * 0.9998 * 0.999) / 1.001
    assert np.isclose(loss, expected)


def test_quantity_and_dollar_pnl_reconcile():
    result = simulate_position_sizing(
        trades((10.0,)), SizingSpec("fixed_25", "fixed_capital", 25), 100, 0.04
    ).iloc[0]
    assert np.isclose(result.asset_quantity, 0.25)
    assert np.isclose(result.net_pnl_usd, 2.5)
    assert np.isclose(result.equity_after_usd, 102.5)
    assert result.allocation_usd <= result.equity_before_usd


def test_overlapping_trades_are_rejected():
    frame = trades()
    frame.loc[1, "entry_timestamp"] = frame.loc[0, "entry_timestamp"]
    with pytest.raises(ValueError, match="overlap"):
        simulate_position_sizing(
            frame, SizingSpec("fixed_25", "fixed_capital", 25), 100, 0.04
        )

