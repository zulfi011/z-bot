"""Causal SOL and BTC trend context at each SOL signal boundary."""

import numpy as np
import pandas as pd


VARIANTS = [
    "all_market_conditions",
    "rising_15d",
    "sol_and_btc_rising_15d",
    "avoid_strong_bearish",
    "avoid_extreme_volatility",
    "avoid_bearish_and_extreme",
    "rising_15d_and_safe",
    "all_filters",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def slope_at_origins(candles, origins, timeframe):
    times = pd.DatetimeIndex(candles.open_time)
    require(times.is_unique and times.is_monotonic_increasing and str(times.tz) == "UTC",
            "Invalid context candle times")
    boundary = pd.DatetimeIndex(origins) - pd.Timedelta(timeframe)
    current_index = times.get_indexer(boundary)
    prior_index = times.get_indexer(boundary - pd.Timedelta("1D"))
    require((current_index >= 0).all(), "Signal boundary missing from context candles")
    values = candles.average_15d.to_numpy(float)
    current = values[current_index]
    prior = np.where(prior_index >= 0, values[np.maximum(prior_index, 0)], np.nan)
    change = (current / prior - 1) * 100
    rising = np.isfinite(current) & np.isfinite(prior) & (change > 1e-12)
    return change, rising


def attach_joint_context(candidates, sol_candles, btc_candles, timeframe):
    output = candidates.copy()
    sol_change, sol_rising = slope_at_origins(sol_candles, output.origin_signal_timestamp, timeframe)
    btc_change, btc_rising = slope_at_origins(btc_candles, output.origin_signal_timestamp, timeframe)
    output["sol_15d_change_24h_pct"] = sol_change
    output["btc_15d_change_24h_pct"] = btc_change
    output["sol_15d_rising"] = sol_rising
    output["btc_15d_rising"] = btc_rising
    output["sol_and_btc_rising_15d"] = sol_rising & btc_rising
    output["strongly_bearish"] = output.origin_regime.eq("bearish")
    return output


def fit_extreme_threshold(candidates):
    training = candidates.loc[
        candidates.eligible & candidates.period.eq("earlier"),
        ["origin_signal_timestamp", "prior_range_24h_pct"],
    ].drop_duplicates("origin_signal_timestamp").dropna()
    require(len(training) >= 100, "Insufficient volatility training origins")
    threshold = float(training.prior_range_24h_pct.quantile(.9))
    require(np.isfinite(threshold) and threshold > 0, "Invalid volatility threshold")
    return threshold, len(training)


def apply_extreme_threshold(candidates, threshold):
    output = candidates.copy()
    output["extreme_volatility"] = (
        output.prior_range_24h_pct.isna() | output.prior_range_24h_pct.gt(threshold)
    )
    return output


def filter_mask(frame, variant):
    rising = frame.sol_15d_rising
    joint = frame.sol_and_btc_rising_15d
    not_bearish = ~frame.strongly_bearish & frame.origin_regime.ne("missing")
    not_extreme = ~frame.extreme_volatility
    masks = {
        "all_market_conditions": pd.Series(True, index=frame.index),
        "rising_15d": rising,
        "sol_and_btc_rising_15d": joint,
        "avoid_strong_bearish": not_bearish,
        "avoid_extreme_volatility": not_extreme,
        "avoid_bearish_and_extreme": not_bearish & not_extreme,
        "rising_15d_and_safe": rising & not_bearish & not_extreme,
        "all_filters": joint & not_bearish & not_extreme,
    }
    require(variant in masks, f"Unknown filter: {variant}")
    return masks[variant]

