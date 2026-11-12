import numpy as np
import pandas as pd
import pytest

from src.backtesting.costs import apply_costs


def trade(raw_entry=100.0, entry_fill=100.02, raw_exit=110.0, exit_fill=109.978):
    return pd.DataFrame([{
        "raw_entry_open": raw_entry,
        "entry_fill": entry_fill,
        "raw_exit_price": raw_exit,
        "exit_fill": exit_fill,
        "return_after_slippage_pct": (exit_fill / entry_fill - 1) * 100,
    }])


def test_entry_and_exit_fees_are_deducted_from_cash_flows():
    result = apply_costs(trade(), 10).iloc[0]
    assert np.isclose(result.entry_fee_per_unit, 100.02 * 0.001)
    assert np.isclose(result.exit_fee_per_unit, 109.978 * 0.001)
    assert np.isclose(result.entry_cash_out_per_unit, 100.02 * 1.001)
    assert np.isclose(result.exit_cash_in_per_unit, 109.978 * 0.999)
    expected = (109.978 * 0.999 / (100.02 * 1.001) - 1) * 100
    assert np.isclose(result.net_return_pct, expected)


def test_slippage_is_measured_without_being_applied_twice():
    result = apply_costs(trade(), 10).iloc[0]
    assert np.isclose(result.entry_slippage_per_unit, 0.02)
    assert np.isclose(result.exit_slippage_per_unit, 0.022)
    assert np.isclose(result.total_slippage_per_unit, 0.042)


def test_zero_fee_preserves_after_slippage_return():
    result = apply_costs(trade(), 0).iloc[0]
    assert np.isclose(result.net_return_pct, result.return_after_slippage_pct)
    assert result.total_fees_per_unit == 0


def test_losses_pay_fees_on_both_sides():
    result = apply_costs(trade(raw_exit=96, exit_fill=95.9808), 10).iloc[0]
    assert result.net_return_pct < result.return_after_slippage_pct < 0
    assert result.total_fees_per_unit > 0


def test_invalid_fee_or_prices_are_rejected():
    with pytest.raises(ValueError, match="Fee rate"):
        apply_costs(trade(), -1)
    invalid = trade()
    invalid.loc[0, "exit_fill"] = 0
    with pytest.raises(ValueError, match="finite and positive"):
        apply_costs(invalid, 10)

