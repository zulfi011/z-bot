import numpy as np
import pandas as pd

from src.backtesting.multi_position import concurrent_metrics, simulate_concurrent_positions
from src.backtesting.position_sizing import SizingSpec


START = pd.Timestamp("2026-01-01", tz="UTC")


def signals():
    return pd.DataFrame([
        {"signal_id": "a", "strategy": "primary", "entry_timestamp": START,
         "exit_timestamp": START + pd.Timedelta(hours=2), "net_return_pct": 10.0},
        {"signal_id": "b", "strategy": "primary", "entry_timestamp": START + pd.Timedelta(hours=1),
         "exit_timestamp": START + pd.Timedelta(hours=3), "net_return_pct": -10.0},
        {"signal_id": "c", "strategy": "primary", "entry_timestamp": START + pd.Timedelta(hours=2),
         "exit_timestamp": START + pd.Timedelta(hours=4), "net_return_pct": 10.0},
    ])


def test_position_limit_changes_how_many_overlapping_signals_open():
    sizing = SizingSpec("equity_25", "equity_fraction", 0.25)
    one = simulate_concurrent_positions(signals(), sizing, 100, 0.04, 1)
    two = simulate_concurrent_positions(signals(), sizing, 100, 0.04, 2)
    assert concurrent_metrics(one, 100)["opened_trades"] == 2
    assert concurrent_metrics(two, 100)["opened_trades"] == 3


def test_exits_release_cash_before_an_entry_at_same_timestamp():
    sizing = SizingSpec("equity_100", "equity_fraction", 1.0)
    events = simulate_concurrent_positions(signals(), sizing, 100, 0.04, 1)
    entry_c = events[(events.signal_id == "c") & (events.event_type == "entry")]
    assert len(entry_c) == 1
    assert np.isclose(entry_c.allocation_usd.iloc[0], 110)


def test_available_cash_caps_positions_without_leverage():
    sizing = SizingSpec("equity_75", "equity_fraction", 0.75)
    events = simulate_concurrent_positions(signals(), sizing, 100, 0.04, 3)
    assert events.cash_usd.min() >= 0
    assert events.deployment_pct.max() <= 100
    assert (events.reason == "partial_cash_fill").any()


def test_risk_sizing_limits_planned_open_risk_per_lot():
    sizing = SizingSpec("risk_1", "risk_fraction", 0.01)
    events = simulate_concurrent_positions(signals(), sizing, 100, 0.04, 2)
    assert events.planned_open_risk_pct.max() <= 2.0 + 1e-12

