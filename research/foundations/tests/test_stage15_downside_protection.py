import numpy as np
import pandas as pd
import pytest

from src.research.stage15_risk.simulator import FixedStopEngine, stop_label
from src.research.stage15_risk.statistics import expected_shortfall_10, summarize_policy


def raw_fixture(lows, highs=None, opens=None, closes=None):
    count = len(lows)
    opens = np.full(count, 100.0) if opens is None else np.asarray(opens, float)
    closes = opens.copy() if closes is None else np.asarray(closes, float)
    highs = np.maximum(opens, closes) if highs is None else np.asarray(highs, float)
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2025-01-01", periods=count, freq="1min", tz="UTC"),
            "open": opens,
            "high": highs,
            "low": np.asarray(lows, float),
            "close": closes,
        }
    )


def test_stop_uses_entry_minute_and_exact_threshold_fill():
    raw = raw_fixture([99.4, *([100.0] * 1439)])
    result = FixedStopEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert bool(result.stop_0_5_hit)
    assert result.stop_0_5_time_minutes == 1
    assert result.stop_0_5_fill_return_pct == pytest.approx(-0.5)
    assert result.stop_0_5_return_24h_pct == pytest.approx(-0.5)
    assert not bool(result.stop_1_hit)


def test_gap_through_stop_uses_trigger_candle_open():
    opens = [100.0, 98.0, *([98.0] * 1438)]
    raw = raw_fixture([100.0, 97.5, *([98.0] * 1438)], opens=opens)
    result = FixedStopEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert result.stop_1_fill_return_pct == pytest.approx(-2.0)
    assert result.stop_1_time_minutes == 2


def test_no_stop_hit_keeps_hold_return():
    closes = [100.0] * 1439 + [102.0]
    raw = raw_fixture([99.9] * 1440, closes=closes)
    result = FixedStopEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert not bool(result.stop_0_5_hit)
    assert result.stop_0_5_return_24h_pct == pytest.approx(2.0)
    assert result.stop_0_5_paired_change_pp == pytest.approx(0.0)


def test_target_stop_order_and_same_minute_ambiguity():
    highs = np.full(1440, 100.0)
    lows = np.full(1440, 100.0)
    highs[2] = 103.0
    lows[4] = 98.0
    row = FixedStopEngine(raw_fixture(lows, highs=highs)).calculate(
        [pd.Timestamp("2025-01-01", tz="UTC")]
    ).iloc[0]
    assert row.stop_1_target_order == "target_first"

    highs[2], lows[2] = 103.0, 98.0
    row = FixedStopEngine(raw_fixture(lows, highs=highs)).calculate(
        [pd.Timestamp("2025-01-01", tz="UTC")]
    ).iloc[0]
    assert row.stop_1_target_order == "ambiguous_same_minute"


def test_incomplete_window_is_unknown():
    raw = raw_fixture([100.0] * 100)
    row = FixedStopEngine(raw).calculate([raw.open_time.iloc[0]]).iloc[0]
    assert not row.stop_window_complete_24h
    assert pd.isna(row.stop_1_hit)
    assert np.isnan(row.stop_1_return_24h_pct)
    assert row.stop_1_target_order == "incomplete"


def test_missing_minutes_rejected():
    raw = raw_fixture([100.0] * 1440).drop(index=10)
    with pytest.raises(ValueError, match="gaps"):
        FixedStopEngine(raw)


def test_direct_replay_validation_and_stable_labels():
    lows = np.full(1500, 100.0)
    lows[30] = 98.5
    highs = np.full(1500, 100.0)
    highs[90] = 103.0
    engine = FixedStopEngine(raw_fixture(lows, highs=highs))
    result = engine.calculate([pd.Timestamp("2025-01-01", tz="UTC")])
    assert engine.validate_samples(result) == 1
    assert stop_label(0.5) == "0_5"
    assert stop_label(2.0) == "2"


def test_summary_counts_recoveries_and_tail():
    frame = pd.DataFrame(
        {
            "audit_hold_return_24h_pct": [2.0, -4.0, 1.0, -1.0],
            "stop_1_hit": pd.array([True, True, False, False], dtype="boolean"),
            "stop_1_return_24h_pct": [-1.0, -1.0, 1.0, -1.0],
            "stop_1_paired_change_pp": [-3.0, 3.0, 0.0, 0.0],
            "stop_1_target_order": ["stop_first", "stop_only", "target_only", "neither"],
            "stop_1_time_minutes": [10.0, 20.0, np.nan, np.nan],
            "stop_1_fill_return_pct": [-1.0, -1.0, np.nan, np.nan],
        }
    )
    summary = summarize_policy(frame, 1.0)
    assert summary["stop_hit_pct"] == 50.0
    assert summary["stopped_trade_improved_pct"] == 50.0
    assert summary["stopped_then_24h_positive_pct"] == 50.0
    assert summary["stopped_before_later_target_pct"] == 50.0
    assert expected_shortfall_10(pd.Series([-4.0, -1.0, 1.0])) == -4.0
