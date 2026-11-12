import numpy as np
import pandas as pd
import pytest

from src.research.stage15_v2_market.context import (
    VARIANTS, apply_extreme_threshold, attach_joint_context, filter_mask,
    fit_extreme_threshold, slope_at_origins,
)


def candle_frame(values):
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=len(values), freq="1h", tz="UTC"),
        "average_15d": values,
    })


def test_slope_uses_value_exactly_24_hours_earlier():
    data = candle_frame(np.r_[np.full(24, 100.), 101., 99.])
    origins = pd.to_datetime(["2025-01-02 01:00", "2025-01-02 02:00"], utc=True)
    change, rising = slope_at_origins(data, origins, "1h")
    assert rising.tolist() == [True, False]
    assert change[0] == pytest.approx(1)


def test_joint_trend_requires_sol_and_btc_to_rise():
    base = pd.DataFrame({"origin_signal_timestamp": pd.to_datetime(["2025-01-02 01:00"], utc=True),
                         "origin_regime": ["neutral"]})
    sol = candle_frame(np.r_[np.full(24, 100.), 101.])
    btc = candle_frame(np.r_[np.full(24, 100.), 99.])
    result = attach_joint_context(base, sol, btc, "1h")
    assert bool(result.sol_15d_rising.iloc[0])
    assert not bool(result.btc_15d_rising.iloc[0])
    assert not bool(result.sol_and_btc_rising_15d.iloc[0])


def test_extreme_threshold_is_fit_only_on_unique_earlier_origins():
    times = pd.date_range("2025-01-01", periods=100, freq="h", tz="UTC")
    frame = pd.DataFrame({"origin_signal_timestamp": np.repeat(times, 2),
                          "prior_range_24h_pct": np.repeat(np.arange(100.), 2),
                          "eligible": True, "period": "earlier"})
    threshold, count = fit_extreme_threshold(frame)
    assert count == 100
    assert threshold == pytest.approx(89.1)


def test_filter_masks_match_declared_logic():
    frame = pd.DataFrame({"sol_15d_rising": [True, True, False],
                          "sol_and_btc_rising_15d": [True, False, False],
                          "strongly_bearish": [False, False, True],
                          "origin_regime": ["bullish", "neutral", "bearish"],
                          "extreme_volatility": [False, True, False]})
    assert filter_mask(frame, "all_filters").tolist() == [True, False, False]
    assert filter_mask(frame, "avoid_strong_bearish").tolist() == [True, True, False]
    assert filter_mask(frame, "avoid_extreme_volatility").tolist() == [True, False, True]
    assert set(VARIANTS) == {"all_market_conditions", "rising_15d", "sol_and_btc_rising_15d",
                             "avoid_strong_bearish", "avoid_extreme_volatility",
                             "avoid_bearish_and_extreme", "rising_15d_and_safe", "all_filters"}
