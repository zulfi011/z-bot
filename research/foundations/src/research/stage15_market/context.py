"""Market context known at the first-touch decision boundary."""

import numpy as np
import pandas as pd


def require(condition, message):
    if not condition:
        raise ValueError(message)


def calculate_context(raw: pd.DataFrame, candles: pd.DataFrame,
                      origins: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Calculate causal context once per episode.

    `origin_signal_timestamp` is the boundary after the first-touch candle.
    Prior range uses the 1,440 completed raw candles immediately before that
    boundary. Prior return compares the last known close with the close known
    exactly 24 hours earlier. Average slope compares values available at the
    touch candle and exactly one day earlier.
    """
    origins = origins.sort_values("origin_signal_timestamp").reset_index(drop=True)
    require(origins.episode_id.is_unique, "Duplicate origin episodes")
    raw_times = pd.DatetimeIndex(raw.open_time)
    candle_times = pd.DatetimeIndex(candles.open_time)
    require(raw_times.is_unique and raw_times.is_monotonic_increasing, "Invalid raw times")
    require(candle_times.is_unique and candle_times.is_monotonic_increasing, "Invalid candle times")
    require(str(raw_times.tz) == "UTC" and str(candle_times.tz) == "UTC", "Times must be UTC")
    require(bool((raw_times[1:] - raw_times[:-1] == pd.Timedelta("1min")).all()), "Raw gaps")
    require(bool((candle_times[1:] - candle_times[:-1] == pd.Timedelta(timeframe)).all()), "Candle gaps")

    origin_times = pd.DatetimeIndex(origins.origin_signal_timestamp)
    start_times = origin_times - pd.Timedelta(timeframe)
    candle_index = candle_times.get_indexer(start_times)
    raw_boundary = raw_times.get_indexer(origin_times)
    require(bool((candle_index >= 0).all() and (raw_boundary >= 0).all()), "Origin not found")

    high = raw.high.to_numpy(float)
    low = raw.low.to_numpy(float)
    close = raw.close.to_numpy(float)
    prior_end = raw_boundary - 1
    prior_start = raw_boundary - 1440
    momentum_anchor = raw_boundary - 1441
    history_available = momentum_anchor >= 0

    prior_range = np.full(len(origins), np.nan)
    prior_return = np.full(len(origins), np.nan)
    for position in np.flatnonzero(history_available):
        left = prior_start[position]
        right = prior_end[position] + 1
        last_close = close[prior_end[position]]
        prior_range[position] = (
            high[left:right].max() - low[left:right].min()
        ) / last_close * 100
        prior_return[position] = (
            last_close / close[momentum_anchor[position]] - 1
        ) * 100

    output = origins[["episode_id", "asset", "timeframe", "average_type", "touch_zone",
                      "origin_signal_timestamp", "approach", "origin_regime",
                      "period", "eligible"]].copy()
    output["prior_return_24h_pct"] = prior_return
    output["prior_range_24h_pct"] = prior_range
    output["prior_return_sign"] = np.where(
        np.isnan(prior_return), "missing",
        np.where(prior_return > 0, "positive", "nonpositive"),
    )

    slope = np.full(len(origins), "missing", dtype=object)
    close_side = np.full(len(origins), "missing", dtype=object)
    average_change = np.full(len(origins), np.nan)
    touch_close_distance = np.full(len(origins), np.nan)
    for average, positions in origins.groupby("average_type", sort=True).groups.items():
        positions = np.asarray(list(positions), dtype=int)
        values = candles[f"average_{average}"].to_numpy(float)
        current_index = candle_index[positions]
        prior_index = candle_times.get_indexer(start_times[positions] - pd.Timedelta("1D"))
        current = values[current_index]
        prior = np.where(prior_index >= 0, values[np.maximum(prior_index, 0)], np.nan)
        valid = np.isfinite(current) & np.isfinite(prior)
        changes = (current / prior - 1) * 100
        average_change[positions] = changes
        slope_values = np.full(len(positions), "missing", dtype=object)
        slope_values[valid & (changes > 1e-12)] = "rising"
        slope_values[valid & (changes < -1e-12)] = "falling"
        slope_values[valid & (np.abs(changes) <= 1e-12)] = "flat"
        slope[positions] = slope_values
        candle_close = candles.close.to_numpy(float)[current_index]
        distance = (candle_close / current - 1) * 100
        touch_close_distance[positions] = distance
        close_side[positions] = np.where(
            np.isfinite(distance),
            np.where(distance > 0, "above_average", "at_or_below_average"),
            "missing",
        )
    output["average_change_24h_pct"] = average_change
    output["average_slope_24h"] = slope
    output["touch_close_distance_pct"] = touch_close_distance
    output["touch_close_side"] = close_side
    output["regime_approach"] = output.origin_regime.astype(str) + "__" + output.approach.astype(str)
    return output


def fit_volatility_thresholds(contexts: pd.DataFrame) -> pd.DataFrame:
    """Fit asset-specific terciles on unique earlier origin timestamps only."""
    unique = contexts.loc[
        contexts.eligible & contexts.period.eq("earlier"),
        ["asset", "origin_signal_timestamp", "prior_range_24h_pct"],
    ].drop_duplicates(["asset", "origin_signal_timestamp"])
    unique = unique.dropna(subset=["prior_range_24h_pct"])
    rows = []
    for asset, group in unique.groupby("asset", sort=True):
        lower, upper = group.prior_range_24h_pct.quantile([1 / 3, 2 / 3])
        require(lower < upper, f"Degenerate volatility thresholds: {asset}")
        rows.append({"asset": asset, "lower_tercile_pct": lower,
                     "upper_tercile_pct": upper, "unique_training_origins": len(group)})
    return pd.DataFrame(rows)


def apply_volatility_bands(contexts: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    output = contexts.merge(thresholds, on="asset", how="left", validate="many_to_one")
    value = output.prior_range_24h_pct
    output["prior_range_band"] = np.select(
        [value.isna(), value <= output.lower_tercile_pct, value <= output.upper_tercile_pct],
        ["missing", "low", "medium"], default="high",
    )
    return output


def reference_context(raw, candles, origin, timeframe):
    """Independent scalar values for validation samples."""
    boundary = pd.Timestamp(origin.origin_signal_timestamp)
    raw_index = pd.DatetimeIndex(raw.open_time).get_loc(boundary)
    candle_index = pd.DatetimeIndex(candles.open_time).get_loc(boundary - pd.Timedelta(timeframe))
    left, right = raw_index - 1440, raw_index
    previous = raw_index - 1441
    if previous < 0:
        prior_return = prior_range = np.nan
    else:
        last = raw.close.iloc[raw_index - 1]
        prior_return = (last / raw.close.iloc[previous] - 1) * 100
        prior_range = (raw.high.iloc[left:right].max() - raw.low.iloc[left:right].min()) / last * 100
    average = f"average_{origin.average_type}"
    current = candles.iloc[candle_index][average]
    prior_time = candles.open_time.iloc[candle_index] - pd.Timedelta("1D")
    prior_positions = np.flatnonzero(candles.open_time.eq(prior_time))
    prior = candles.iloc[prior_positions[0]][average] if len(prior_positions) else np.nan
    change = (current / prior - 1) * 100 if pd.notna(current) and pd.notna(prior) else np.nan
    distance = (candles.close.iloc[candle_index] / current - 1) * 100
    return prior_return, prior_range, change, distance
