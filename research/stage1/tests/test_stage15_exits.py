import numpy as np
import pandas as pd
import pytest

from src.research.stage15_exit.simulator import ExitEngine


def fixture(opens=None, highs=None, lows=None, closes=None, count=1500):
    opens = np.full(count, 100.0) if opens is None else np.asarray(opens, float)
    closes = opens.copy() if closes is None else np.asarray(closes, float)
    highs = np.maximum(opens, closes) if highs is None else np.asarray(highs, float)
    lows = np.minimum(opens, closes) if lows is None else np.asarray(lows, float)
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=count, freq="1min", tz="UTC"),
        "open": opens, "high": highs, "low": lows, "close": closes,
    })


def test_fixed_time_uses_requested_minute_close():
    closes = np.full(1500, 100.0)
    closes[14], closes[29], closes[59] = 101.0, 102.0, 103.0
    raw = fixture(highs=np.maximum(100.0, closes), lows=np.minimum(100.0, closes), closes=closes)
    row = ExitEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert row.time_15_no_stop_return_pct == pytest.approx(1.0)
    assert row.time_30_no_stop_return_pct == pytest.approx(2.0)
    assert row.time_60_no_stop_return_pct == pytest.approx(3.0)


def test_target_fills_at_threshold_and_gap_open():
    highs = np.full(1500, 100.0)
    highs[4] = 102.0
    row = ExitEngine(fixture(highs=highs)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert row.target_1_no_stop_return_pct == pytest.approx(1.0)
    assert row.target_1_no_stop_duration_minutes == 5
    opens = np.full(1500, 100.0)
    opens[4:] = 102.0
    highs[4:] = 102.0
    lows = np.minimum(opens, 100.0)
    row = ExitEngine(fixture(opens=opens, highs=highs, lows=lows)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert row.target_1_no_stop_return_pct == pytest.approx(2.0)


def test_target_stop_same_minute_is_conservative():
    highs, lows = np.full(1500, 100.0), np.full(1500, 100.0)
    highs[10], lows[10] = 103.0, 95.0
    row = ExitEngine(fixture(highs=highs, lows=lows)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert row.target_2_5_stop_4_return_pct == pytest.approx(-4.0)
    assert row.target_2_5_stop_4_exit_type == "ambiguous_stop"


def test_stop_only_applies_when_before_time_exit():
    lows = np.full(1500, 100.0)
    lows[20] = 95.0
    row = ExitEngine(fixture(lows=lows)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert row.time_15_stop_4_exit_type == "time"
    assert row.time_30_stop_4_exit_type == "protective_stop"


def test_trail_starts_after_activation_and_uses_prior_peak():
    opens = np.full(1500, 100.0)
    opens[6:] = 102.0
    highs, lows = opens.copy(), opens.copy()
    highs[5], lows[5] = 103.0, 98.0
    lows[6] = 101.0
    row = ExitEngine(fixture(opens=opens, highs=highs, lows=lows)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert row.trail_50_no_stop_exit_type == "trailing_stop"
    assert row.trail_50_no_stop_duration_minutes == 7
    assert row.trail_50_no_stop_return_pct == pytest.approx(1.5)


def test_unactivated_trail_holds_to_24h():
    closes = np.full(1500, 100.0)
    closes[1439] = 101.0
    raw = fixture(highs=np.maximum(100.0, closes), lows=np.minimum(100.0, closes), closes=closes)
    row = ExitEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert row.trail_30_no_stop_exit_type == "time"
    assert row.trail_30_no_stop_return_pct == pytest.approx(1.0)


def test_four_percent_stop_protects_before_trailing_activation():
    highs, lows = np.full(1500, 100.0), np.full(1500, 100.0)
    lows[20] = 95.0
    row = ExitEngine(fixture(highs=highs, lows=lows)).calculate(
        [pd.Timestamp("2025-01-01", tz="UTC")]
    ).iloc[0]
    assert row.trail_30_no_stop_exit_type == "time"
    assert row.trail_30_stop_4_exit_type == "protective_stop"
    assert row.trail_30_stop_4_return_pct == pytest.approx(-4.0)


def test_incomplete_and_gapped_data_are_rejected_or_unknown():
    raw = fixture(count=100)
    row = ExitEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert not row.exit_window_complete_24h
    assert np.isnan(row.target_1_no_stop_return_pct)
    with pytest.raises(ValueError, match="gaps"):
        ExitEngine(raw.drop(index=4))


def test_scalar_replay_validates_all_exit_families():
    highs, lows = np.full(1500, 100.0), np.full(1500, 100.0)
    highs[100], highs[200] = 103.0, 104.0
    lows[300] = 99.0
    engine = ExitEngine(fixture(highs=highs, lows=lows))
    result = engine.calculate([pd.Timestamp("2025-01-01", tz="UTC")])
    assert engine.validate_samples(result) == 1
