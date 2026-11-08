import numpy as np
import pandas as pd

from src.backtesting.account import build_account_curve, select_spot_lots


START = pd.Timestamp("2026-01-01", tz="UTC")


def candles():
    return pd.DataFrame({
        "open_time": pd.date_range(START, periods=5, freq="1min"),
        "open": [10, 11, 12, 13, 14],
        "close": [11, 12, 13, 14, 15],
    })


def outcomes():
    rows = []
    for signal, entry, exit_, entry_cost, exit_cash in [
        ("a", START, START + pd.Timedelta(minutes=2), 10.0, 12.0),
        ("b", START + pd.Timedelta(minutes=1), START + pd.Timedelta(minutes=4), 11.0, 14.0),
        ("c", START + pd.Timedelta(minutes=1), START + pd.Timedelta(minutes=3), 11.0, 13.0),
    ]:
        rows.append({
            "signal_id": signal,
            "entry_timestamp": entry,
            "exit_timestamp": exit_,
            "entry_cash_out_per_unit": entry_cost,
            "exit_cash_in_per_unit": exit_cash,
            "net_pnl_per_unit": exit_cash - entry_cost,
            "entry_fee_per_unit": 0.01,
            "exit_fee_per_unit": 0.01,
        })
    return pd.DataFrame(rows)


def test_selection_uses_two_slots_and_current_marked_equity():
    selected = select_spot_lots(outcomes(), candles(), 100, 0.25, 2)
    assert selected.signal_id.tolist() == ["a", "b"]
    assert np.isclose(selected.allocation_usd.iloc[0], 25)
    # At minute one: $75 cash plus 2.5 SOL marked at the known $11 open.
    assert np.isclose(selected.equity_at_entry_usd.iloc[1], 102.5)
    assert np.isclose(selected.allocation_usd.iloc[1], 25.625)


def test_curve_records_close_marking_and_realized_pnl_every_minute():
    selected = select_spot_lots(outcomes().iloc[[0]], candles(), 100, 0.25, 2)
    curve = build_account_curve(candles(), selected, 100)
    assert len(curve) == len(candles())
    assert np.isclose(curve.iloc[0].cash_usd, 75)
    assert np.isclose(curve.iloc[0].open_position_value_usd, 27.5)
    assert np.isclose(curve.iloc[0].total_equity_usd, 102.5)
    # The exit at 00:02 is reflected after the 00:01 candle closes.
    assert curve.iloc[1].open_positions == 0
    assert np.isclose(curve.iloc[1].realized_pnl_usd, 5)
    assert np.isclose(curve.iloc[1].total_equity_usd, 105)
    assert np.allclose(curve.total_equity_usd - 100, curve.total_pnl_usd)


def test_exit_cash_is_available_to_an_entry_at_same_boundary():
    data = outcomes().iloc[[0]].copy()
    replacement = data.iloc[0].copy()
    replacement.signal_id = "d"
    replacement.entry_timestamp = START + pd.Timedelta(minutes=2)
    replacement.exit_timestamp = START + pd.Timedelta(minutes=5)
    data = pd.concat([data, replacement.to_frame().T], ignore_index=True)
    extended = pd.concat([
        candles(),
        pd.DataFrame({"open_time": [START + pd.Timedelta(minutes=5)], "open": [15], "close": [15]}),
    ], ignore_index=True)
    selected = select_spot_lots(data, extended, 100, 0.25, 1)
    assert selected.signal_id.tolist() == ["a", "d"]
    assert selected.allocation_usd.iloc[1] > 25

