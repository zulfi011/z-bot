import numpy as np
import pandas as pd
import pytest

from src.research.stage15_v2_bounce.signals import POLICIES, generate_candidates
from src.research.stage15_v2_bounce.simulator import FixedExitEngine


def candles(closes, highs=None):
    closes = np.asarray(closes, float)
    highs = np.asarray(highs if highs is not None else closes + .1, float)
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=len(closes), freq="5min", tz="UTC"),
        "open": closes, "high": highs, "low": closes - .1, "close": closes,
        "average_15d": np.full(len(closes), 100.),
    })


def episodes():
    return pd.DataFrame({
        "episode_id": ["e"], "asset": ["SOLUSDT"], "timeframe": ["5m"],
        "average_type": ["15d"], "touch_zone": [.5],
        "start_timestamp": [pd.Timestamp("2025-01-01 00:05", tz="UTC")],
        "left_censored": [False],
    })


def test_reclaim_then_later_break_enters_next_candle():
    data = candles([99, 100.2, 100.3, 100.5, 100.6], [99.2, 100.4, 100.35, 100.6, 100.7])
    result = generate_candidates(data, episodes(), "5m").set_index("policy")
    assert result.index.tolist() == POLICIES
    assert result.loc["bounce_break_15m", "status"] == "confirmed"
    assert result.loc["bounce_break_15m", "reclaim_candle_timestamp"] == data.open_time.iloc[1]
    assert result.loc["bounce_break_15m", "breakout_candle_timestamp"] == data.open_time.iloc[3]
    assert result.loc["bounce_break_15m", "entry_timestamp"] == data.open_time.iloc[4]


def test_same_reclaim_candle_cannot_also_be_breakout():
    data = candles([99, 101] + [100.5] * 8, [99.2, 105] + [104] * 8)
    result = generate_candidates(data, episodes(), "5m")
    assert result.status.eq("expired_breakout_window").all()


def test_close_back_below_average_invalidates_waiting_setup():
    data = candles([99, 100.2, 99.9, 101, 101], [99.2, 100.4, 100.3, 101.2, 101.2])
    result = generate_candidates(data, episodes(), "5m")
    assert result.status.eq("invalidated").all()


def test_immediate_requires_next_candle_but_longer_windows_can_confirm():
    data = candles([99, 100.2, 100.3, 100.5, 100.6], [99.2, 100.4, 100.35, 100.6, 100.7])
    result = generate_candidates(data, episodes(), "5m").set_index("policy")
    assert result.loc["bounce_break_immediate", "status"] == "expired_breakout_window"
    assert result.loc["bounce_break_15m", "status"] == "confirmed"
    assert result.loc["bounce_break_30m", "status"] == "confirmed"


def raw_minutes(highs, lows, closes=None, opens=None):
    highs = np.asarray(highs, float); lows = np.asarray(lows, float)
    opens = np.asarray(opens if opens is not None else np.full(len(highs), 100.), float)
    closes = np.asarray(closes if closes is not None else opens, float)
    return pd.DataFrame({"open_time": pd.date_range("2025-01-01", periods=len(highs), freq="1min", tz="UTC"),
                         "open": opens, "high": highs, "low": lows, "close": closes})


@pytest.mark.parametrize("hit_index,expected", [(3, "profit_target"), (5, "protective_stop")])
def test_fixed_exit_first_hit(hit_index, expected):
    size = 1441; highs = np.full(size, 101.); lows = np.full(size, 99.)
    if expected == "profit_target": highs[hit_index] = 104
    else: lows[hit_index] = 96
    result = FixedExitEngine(raw_minutes(highs, lows)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert result.exit_type == expected
    assert result.duration_minutes == hit_index + 1
    assert abs(result.gross_return_pct) == pytest.approx(4)


def test_same_minute_target_and_stop_uses_stop():
    size = 1441; highs = np.full(size, 101.); lows = np.full(size, 99.)
    highs[2] = 104; lows[2] = 96
    result = FixedExitEngine(raw_minutes(highs, lows)).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert result.exit_type == "ambiguous_stop"
    assert result.gross_return_pct == pytest.approx(-4)
