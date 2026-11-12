"""Causal episode-local confirmations; no future outcome or episode-end input."""

import numpy as np
import pandas as pd

RULES = ["bullish_candle", "close_above_average", "reclaim_average",
         "bullish_above_average", "close_above_zone", "break_touch_high"]
WAITS = [15, 30, 60]
KEYS = ["asset", "timeframe", "average_type", "touch_zone"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def policy_list():
    return [("first_touch", 0)] + [(rule, wait) for rule in RULES for wait in WAITS]


def conditions(rule, close, opened, average, previous_close, previous_average, first_high, zone):
    if rule == "first_touch":
        return np.ones_like(close, dtype=bool)
    if rule == "bullish_candle":
        return close > opened
    if rule == "close_above_average":
        return close > average
    if rule == "reclaim_average":
        return (previous_close <= previous_average) & (close > average)
    if rule == "bullish_above_average":
        return (close > opened) & (close > average)
    if rule == "close_above_zone":
        return close > average * (1 + zone / 100)
    if rule == "break_touch_high":
        return close > first_high
    raise ValueError(rule)


def generate_candidates(candles, episodes, timeframe):
    """One auditable row per episode and policy, including unconfirmed episodes.

    The first-touch candle can itself confirm. First non-touch candle is a final
    confirmation opportunity, then pending state is cancelled. All decisions
    become available at the candle's closing boundary, never at its open.
    """
    times = pd.DatetimeIndex(candles.open_time)
    delta = pd.Timedelta(timeframe)
    require(times.is_monotonic_increasing and times.is_unique and str(times.tz) == "UTC", "Invalid candle times")
    require((times[1:] - times[:-1] == delta).all(), "Irregular candle grid")
    require(episodes.episode_id.is_unique, "Duplicate episodes")
    opened = candles.open.to_numpy(float)
    closes = candles.close.to_numpy(float)
    highs = candles.high.to_numpy(float)
    lows = candles.low.to_numpy(float)
    frames = []
    for (average, zone), group in episodes.groupby(["average_type", "touch_zone"], sort=True):
        group = group.reset_index(drop=True)
        start = times.get_indexer(group.start_timestamp)
        require((start >= 0).all(), "Episode not in candles")
        values = candles[f"average_{average}"].to_numpy(float)
        touched = np.isfinite(values) & (highs >= values*(1-zone/100)) & (lows <= values*(1+zone/100))
        require(touched[start].all(), "Episode starts without a touch")
        require((~touched[np.maximum(start-1, 0)] | (start == 0)).all(), "Not a first-touch episode")
        previous = np.maximum(start-1, 0)
        approach = np.full(len(group), "unknown", object)
        prior_valid = (start > 0) & np.isfinite(values[previous])
        approach[prior_valid & (lows[previous] > values[previous]*(1+zone/100))] = "from_above"
        approach[prior_valid & (highs[previous] < values[previous]*(1-zone/100))] = "from_below"
        all_average = candles[["average_7d", "average_15d", "average_30d"]].to_numpy(float)[start]
        regime = np.full(len(group), "missing", object)
        complete_average = np.isfinite(all_average).all(axis=1)
        regime[complete_average] = "neutral"
        regime[complete_average & (all_average[:, 0] > all_average[:, 1]) & (all_average[:, 1] > all_average[:, 2])] = "bullish"
        regime[complete_average & (all_average[:, 0] < all_average[:, 1]) & (all_average[:, 1] < all_average[:, 2])] = "bearish"
        for rule, wait in policy_list():
            offsets = np.arange(wait // int(delta.total_seconds()/60) + 1)
            indices = start[:, None] + offsets
            exists = indices < len(times)
            safe = np.minimum(indices, len(times)-1)
            # A first exit candle is allowed, all subsequent candles are not.
            exits = ~touched[safe] & exists
            prior_exits = np.cumsum(exits, axis=1) - exits
            allowed = exists & (prior_exits == 0) & np.isfinite(values[safe])
            previous_indices = np.maximum(safe-1, 0)
            matches = conditions(rule, closes[safe], opened[safe], values[safe],
                                 closes[previous_indices], values[previous_indices],
                                 highs[start, None], zone)
            if rule == "reclaim_average":
                matches &= safe > 0
            matches &= allowed
            confirmed = matches.any(axis=1)
            first = matches.argmax(axis=1)
            signal_index = safe[np.arange(len(group)), first]
            status = np.where(exits.any(axis=1), "cancelled_at_episode_exit",
                              np.where(exists.all(axis=1), "expired_wait_limit", "truncated_data_end"))
            status[confirmed] = "confirmed"
            result = group[["episode_id", *KEYS, "representative_event_id", "start_timestamp", "left_censored"]].copy()
            result["rule"] = rule
            result["wait_minutes"] = wait
            result["policy"] = f"{rule}_{wait}m"
            result["status"] = status
            result["origin_signal_timestamp"] = pd.DatetimeIndex(group.start_timestamp) + delta
            result["approach"] = approach
            result["origin_regime"] = regime
            result["signal_candle_timestamp"] = pd.Series(times[signal_index]).where(confirmed)
            result["entry_timestamp"] = (pd.Series(times[signal_index]) + delta).where(confirmed)
            result["delay_minutes"] = np.where(confirmed, first * delta.total_seconds()/60, np.nan)
            result["confirmation_close"] = np.where(confirmed, closes[signal_index], np.nan)
            frames.append(result)
    result = pd.concat(frames, ignore_index=True)
    require(not result.duplicated(["episode_id", "policy"]).any(), "Duplicate candidate")
    return result


def reference_signal(candles, start_index, average, zone, rule, wait, timeframe):
    """Independent scalar replay for validation only."""
    step = int(pd.Timedelta(timeframe).total_seconds()/60)
    first_high = candles.iloc[start_index].high
    for index in range(start_index, min(start_index + wait//step + 1, len(candles))):
        row = candles.iloc[index]
        value = row[f"average_{average}"]
        if pd.isna(value):
            return None
        previous = candles.iloc[index-1] if index else None
        if rule == "first_touch":
            yes = True
        elif rule == "bullish_candle":
            yes = row.close > row.open
        elif rule == "close_above_average":
            yes = row.close > value
        elif rule == "reclaim_average":
            yes = previous is not None and previous.close <= previous[f"average_{average}"] and row.close > value
        elif rule == "bullish_above_average":
            yes = row.close > row.open and row.close > value
        elif rule == "close_above_zone":
            yes = row.close > value*(1+zone/100)
        elif rule == "break_touch_high":
            yes = row.close > first_high
        else:
            raise ValueError(rule)
        if yes:
            return row.open_time + pd.Timedelta(timeframe)
        touched = row.high >= value*(1-zone/100) and row.low <= value*(1+zone/100)
        if not touched:
            return None
    return None
