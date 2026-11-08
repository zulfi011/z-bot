import numpy as np
import pandas as pd

from src.backtesting.scenarios import rebuild_cost_scenario_outcomes


START = pd.Timestamp("2026-01-01", tz="UTC")


def test_cost_scenario_rebuilds_entry_threshold_and_cash_costs():
    raw = pd.DataFrame({
        "open_time": pd.date_range(START, periods=2, freq="1min"),
        "open": [100.0, 100.0], "high": [105.0, 101.0],
        "low": [99.0, 99.0], "close": [104.0, 100.0],
    })
    fills = pd.DataFrame([{
        "signal_id": "c", "strategy": "control", "timestamp": START,
        "raw_open": 100.0,
    }])
    outcomes, incomplete = rebuild_cost_scenario_outcomes(
        fills, raw, fee_bps_per_side=20, slippage_bps_per_side=10,
        maximum_hold_minutes=2,
    )
    row = outcomes.iloc[0]
    assert incomplete.empty
    assert np.isclose(row.entry_fill, 100.1)
    assert row.exit_type == "profit_target"
    assert np.isclose(row.raw_exit_price, 104.104)
    assert np.isclose(row.exit_fill, 104.104 * 0.999)
    assert np.isclose(row.entry_fee_per_unit, row.entry_fill * 0.002)
    assert np.isclose(row.exit_fee_per_unit, row.exit_fill * 0.002)

