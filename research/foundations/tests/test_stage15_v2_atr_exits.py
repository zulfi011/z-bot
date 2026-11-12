import numpy as np
import pandas as pd
import pytest

from src.research.stage15_v2_atr.atr import attach_entry_atr, hourly_candles, wilder_atr
from src.research.stage15_v2_atr.simulator import AtrExitEngine, strategy_name


def raw_frame(periods=1441):
    opened = np.full(periods, 100.)
    return pd.DataFrame({"open_time": pd.date_range("2025-01-01", periods=periods, freq="1min", tz="UTC"),
                         "open": opened, "high": opened + 1, "low": opened - 1, "close": opened})


def test_hourly_resample_uses_complete_groups():
    raw = raw_frame(120)
    hourly = hourly_candles(raw)
    assert len(hourly) == 2
    assert hourly["count"].tolist() == [60, 60]


def test_wilder_atr_seeds_with_first_fourteen_true_ranges():
    candles = pd.DataFrame({"high": np.full(15, 102.), "low": np.full(15, 98.),
                            "close": np.full(15, 100.)})
    atr, true_range = wilder_atr(candles)
    assert np.isnan(atr[12])
    assert atr[13] == pytest.approx(4)
    assert atr[14] == pytest.approx(4)
    assert (true_range == 4).all()


def test_entry_atr_uses_previous_completed_hour():
    hourly = pd.DataFrame({"open_time": pd.date_range("2025-01-01", periods=20, freq="1h", tz="UTC")})
    atr = np.arange(20, dtype=float)
    result = attach_entry_atr(pd.to_datetime(["2025-01-01 15:00", "2025-01-01 15:37"], utc=True), hourly, atr)
    assert result.atr_reference_hour.tolist() == [pd.Timestamp("2025-01-01 14:00", tz="UTC")] * 2
    assert result.atr_14_1h.tolist() == [14, 14]


def test_atr_exit_is_long_spot_target_and_stop():
    raw = raw_frame()
    raw.loc[10, "high"] = 104
    engine = AtrExitEngine(raw)
    context = pd.DataFrame({"entry_timestamp": [pd.Timestamp("2025-01-01", tz="UTC")],
                            "atr_reference_hour": [pd.Timestamp("2024-12-31 23:00", tz="UTC")],
                            "atr_14_1h": [1.]})
    result = engine.calculate(context).iloc[0]
    strategy = strategy_name(1.5, 2.5)
    assert result[f"{strategy}_target_distance_pct"] == pytest.approx(3.75)
    assert result[f"{strategy}_stop_distance_pct"] == pytest.approx(1.5)
    assert result[f"{strategy}_return_pct"] == pytest.approx(3.75)
    assert result[f"{strategy}_exit_type"] == "profit_target"


def test_same_minute_target_and_stop_is_conservative_stop():
    raw = raw_frame(); raw.loc[5, "high"] = 105; raw.loc[5, "low"] = 95
    engine = AtrExitEngine(raw)
    context = pd.DataFrame({"entry_timestamp": [pd.Timestamp("2025-01-01", tz="UTC")],
                            "atr_reference_hour": [pd.Timestamp("2024-12-31 23:00", tz="UTC")],
                            "atr_14_1h": [2.]})
    result = engine.calculate(context).iloc[0]
    strategy = strategy_name(1.5, 1.5)
    assert result[f"{strategy}_exit_type"] == "ambiguous_stop"
    assert result[f"{strategy}_return_pct"] == pytest.approx(-3)

