"""Causal context and condition-statistics tests for Stage 1.5 Step 3."""

import numpy as np
import pandas as pd
import pytest

from src.research.stage15_market.context import (
    apply_volatility_bands, calculate_context, fit_volatility_thresholds, reference_context,
)
from src.research.stage15_market.statistics import (
    attach_screen_intervals, block_difference_interval, build_condition_summaries,
    build_stability_screen, metrics,
)


def fixtures():
    raw_times = pd.date_range("2024-12-30", periods=5000, freq="1min", tz="UTC")
    prices = 100 + np.arange(5000) / 1000
    raw = pd.DataFrame({
        "open_time": raw_times, "open": prices, "high": prices + 1,
        "low": prices - 1, "close": prices + .1,
    })
    candle_times = pd.date_range("2024-12-30", periods=1000, freq="5min", tz="UTC")
    candles = pd.DataFrame({
        "open_time": candle_times, "open": 100., "high": 101., "low": 99., "close": 100.5,
    })
    for average in ["7d", "15d", "30d"]:
        candles[f"average_{average}"] = 100 + np.arange(1000) / 10000
    starts = [400, 700]
    origins = pd.DataFrame({
        "episode_id": ["a", "b"], "asset": "TEST", "timeframe": "5m",
        "average_type": ["15d", "15d"], "touch_zone": [.5, .5],
        "origin_signal_timestamp": candle_times[starts] + pd.Timedelta("5min"),
        "approach": ["from_above", "from_below"], "origin_regime": ["bullish", "neutral"],
        "period": ["earlier", "later"], "eligible": True,
    })
    return raw, candles, origins


def test_context_matches_independent_scalar_calculation():
    raw, candles, origins = fixtures()
    result = calculate_context(raw, candles, origins, "5m").set_index("episode_id")
    for origin in origins.itertuples(index=False):
        expected = reference_context(raw, candles, origin, "5m")
        actual = result.loc[origin.episode_id]
        for column, value in zip(
            ["prior_return_24h_pct", "prior_range_24h_pct",
             "average_change_24h_pct", "touch_close_distance_pct"], expected,
        ):
            assert actual[column] == pytest.approx(value)
    assert result.average_slope_24h.eq("rising").all()
    assert result.prior_return_sign.eq("positive").all()
    assert result.touch_close_side.eq("above_average").all()


def test_future_price_changes_do_not_change_context():
    raw, candles, origins = fixtures()
    original = calculate_context(raw, candles, origins.iloc[:1], "5m")
    boundary = origins.origin_signal_timestamp.iloc[0]
    raw.loc[raw.open_time >= boundary, ["high", "low", "close"]] = 9999.
    candles.loc[candles.open_time >= boundary, "average_15d"] = 9999.
    changed = calculate_context(raw, candles, origins.iloc[:1], "5m")
    pd.testing.assert_frame_equal(original, changed)


def test_prior_range_uses_exactly_1440_completed_minutes():
    raw, candles, origins = fixtures()
    boundary = origins.origin_signal_timestamp.iloc[0]
    outside = raw.index[raw.open_time.eq(boundary - pd.Timedelta("1441min"))][0]
    inside = raw.index[raw.open_time.eq(boundary - pd.Timedelta("1440min"))][0]
    baseline = calculate_context(raw, candles, origins.iloc[:1], "5m").prior_range_24h_pct.iloc[0]
    raw.loc[outside, "high"] = 99999.
    assert calculate_context(raw, candles, origins.iloc[:1], "5m").prior_range_24h_pct.iloc[0] == baseline
    raw.loc[inside, "high"] = 99999.
    assert calculate_context(raw, candles, origins.iloc[:1], "5m").prior_range_24h_pct.iloc[0] > baseline


def test_missing_history_remains_missing():
    raw, candles, origins = fixtures()
    origins.loc[0, "origin_signal_timestamp"] = candles.open_time.iloc[100] + pd.Timedelta("5min")
    result = calculate_context(raw, candles, origins.iloc[:1], "5m")
    assert pd.isna(result.prior_return_24h_pct.iloc[0])
    assert result.prior_return_sign.iloc[0] == "missing"


def test_irregular_data_rejected():
    raw, candles, origins = fixtures()
    with pytest.raises(ValueError, match="Raw gaps"):
        calculate_context(raw.drop(index=10), candles, origins, "5m")


def test_volatility_thresholds_use_unique_earlier_origins_only():
    frame = pd.DataFrame({
        "asset": ["A"] * 8, "origin_signal_timestamp": pd.to_datetime(
            ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-03",
             "2025-01-04", "2025-10-01", "2025-10-02", "2025-10-03"], utc=True),
        "prior_range_24h_pct": [1., 1., 2., 3., 4., 100., 200., 300.],
        "eligible": True, "period": ["earlier"] * 5 + ["later"] * 3,
    })
    threshold = fit_volatility_thresholds(frame).iloc[0]
    expected = pd.Series([1., 2., 3., 4.]).quantile([1/3, 2/3])
    assert threshold.lower_tercile_pct == pytest.approx(expected.iloc[0])
    assert threshold.upper_tercile_pct == pytest.approx(expected.iloc[1])
    applied = apply_volatility_bands(frame, pd.DataFrame([threshold]))
    assert applied.prior_range_band.iloc[-1] == "high"


def outcome_frame(n=480):
    times = pd.date_range("2025-01-01", periods=n, freq="6h", tz="UTC")
    condition = np.where(np.arange(n) % 2 == 0, "bullish", "neutral")
    returns = np.where(condition == "bullish", 2., -1.)
    return pd.DataFrame({
        "asset": "A", "timeframe": "5m", "average_type": "15d", "touch_zone": .5,
        "rule": "first_touch", "wait_minutes": 0, "policy": "first_touch_0m",
        "period": np.where(times < pd.Timestamp("2025-03-01", tz="UTC"), "earlier", "later"),
        "eligible": True, "entered": True, "origin_signal_timestamp": times,
        "return_1440m_pct": returns, "mae_1440m_pct": -1., "mfe_1440m_pct": 2.,
        "target_2_5_reached": returns > 0, "first_2.5": np.where(returns > 0, "target_first", "stop_first"),
        "origin_regime": condition, "approach": "from_above", "average_slope_24h": "rising",
        "prior_return_sign": "positive", "prior_range_band": "medium",
        "touch_close_side": "above_average", "regime_approach": condition + "__from_above",
    })


def test_metrics_and_complement_are_kept_separate():
    frame = outcome_frame()
    result = metrics(frame)
    assert result["entries"] == len(frame)
    assert result["return_24h_mean_pct"] == .5
    summary = build_condition_summaries(frame)
    bullish = summary.loc[
        summary.period.eq("all") & summary.condition.eq("origin_regime")
        & summary.value.eq("bullish")
    ].iloc[0]
    assert bullish.return_24h_mean_pct == 2.
    assert bullish.complement_return_24h_mean_pct == -1.
    assert bullish.mean_advantage_vs_complement_pp == 3.


def test_block_interval_detects_constant_difference():
    frame = outcome_frame()
    selected = frame.loc[frame.origin_regime.eq("bullish")]
    complement = frame.loc[frame.origin_regime.eq("neutral")]
    low, high, blocks = block_difference_interval(selected, complement)
    assert low == high == 3.
    assert blocks >= 8


def test_stability_screen_requires_both_periods_and_complement_advantage():
    summary = build_condition_summaries(outcome_frame())
    screen = build_stability_screen(summary)
    bullish = screen.loc[
        screen.condition.eq("origin_regime") & screen.value.eq("bullish")
    ].iloc[0]
    assert bullish.stability_screen
    neutral = screen.loc[
        screen.condition.eq("origin_regime") & screen.value.eq("neutral")
    ].iloc[0]
    assert not neutral.stability_screen
    audited = attach_screen_intervals(screen, outcome_frame())
    bullish = audited.loc[
        audited.condition.eq("origin_regime") & audited.value.eq("bullish")
    ].iloc[0]
    assert bullish.positive_block_ci_both
