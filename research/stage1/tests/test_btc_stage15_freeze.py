import numpy as np
import pandas as pd
import pytest

from src.research.btc_stage15_freeze.run import replay


def candles(highs, lows, closes=None):
    size = len(highs)
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2026-01-01", periods=size, freq="1min", tz="UTC"),
            "open": np.full(size, 100.0),
            "high": highs,
            "low": lows,
            "close": closes if closes is not None else np.full(size, 100.0),
        }
    )


def one_signal():
    return pd.DataFrame({"entry_timestamp": [pd.Timestamp("2026-01-01", tz="UTC")]})


def test_no_stop_time_exit_is_finite():
    result = replay(one_signal(), candles([100, 100, 100], [99, 99, 99]), 0, 0, hold_minutes=3)
    assert result.iloc[0].exit_type == "time"
    assert np.isfinite(result.iloc[0].net_return_pct)


def test_profit_target_uses_actual_entry_fill():
    result = replay(one_signal(), candles([101.1, 100, 100], [100, 99, 99]), 0, 0, hold_minutes=3)
    assert result.iloc[0].exit_type == "profit_target"
    assert result.iloc[0].net_return_pct == pytest.approx(1.0)


def test_same_minute_target_stop_conflict_chooses_stop():
    result = replay(one_signal(), candles([102, 100, 100], [97, 99, 99]), 0, 0, stop_pct=2, hold_minutes=3)
    assert result.iloc[0].exit_type == "protective_stop"
    assert result.iloc[0].net_return_pct == pytest.approx(-2.0)
