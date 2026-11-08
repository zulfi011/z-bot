"""Causal two-stage reclaim and breakout signals for deduplicated touches."""

import numpy as np
import pandas as pd


KEYS = ["asset", "timeframe", "average_type", "touch_zone"]
POLICIES = ["bounce_break_immediate", "bounce_break_15m", "bounce_break_30m"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _approach_from_below(start, highs, averages, zone):
    if start == 0 or not np.isfinite(averages[start - 1]):
        return False
    return highs[start - 1] < averages[start - 1] * (1 - zone / 100)


def _find_signal(candles, start, average_column, timeframe, policy):
    """Return reclaim and breakout indices, status, and cancellation reason."""
    step = int(pd.Timedelta(timeframe).total_seconds() / 60)
    reclaim_steps = 30 // step
    break_minutes = {"bounce_break_immediate": step, "bounce_break_15m": 15,
                     "bounce_break_30m": 30}[policy]
    break_steps = max(1, break_minutes // step)
    averages = candles[average_column].to_numpy(float)
    closes = candles.close.to_numpy(float)
    highs = candles.high.to_numpy(float)

    reclaim = None
    reclaim_last = min(start + reclaim_steps, len(candles) - 1)
    for index in range(start, reclaim_last + 1):
        if not np.isfinite(averages[index]):
            return None, None, "invalid_average", "missing_average"
        if closes[index] > averages[index]:
            reclaim = index
            break
    if reclaim is None:
        status = "truncated_data_end" if reclaim_last == len(candles) - 1 else "no_reclaim"
        return None, None, status, "reclaim_not_found"

    breakout_last = min(reclaim + break_steps, len(candles) - 1)
    for index in range(reclaim + 1, breakout_last + 1):
        if not np.isfinite(averages[index]):
            return reclaim, None, "invalid_average", "missing_average"
        if closes[index] <= averages[index]:
            return reclaim, None, "invalidated", "closed_back_at_or_below_average"
        if highs[index] > highs[reclaim]:
            return reclaim, index, "confirmed", "confirmed"
    status = "truncated_data_end" if breakout_last == len(candles) - 1 else "expired_breakout_window"
    return reclaim, None, status, "breakout_not_found"


def generate_candidates(candles, episodes, timeframe):
    """Generate three strictly ordered bounce policies for from-below episodes."""
    candles = candles.reset_index(drop=True)
    times = pd.DatetimeIndex(candles.open_time)
    delta = pd.Timedelta(timeframe)
    require(times.is_monotonic_increasing and times.is_unique and str(times.tz) == "UTC",
            "Invalid candle timestamps")
    require((times[1:] - times[:-1] == delta).all(), "Irregular source candle grid")
    require(episodes.episode_id.is_unique, "Duplicate episodes")
    highs = candles.high.to_numpy(float)
    rows = []
    for (average, zone), group in episodes.groupby(["average_type", "touch_zone"], sort=True):
        average_column = f"average_{average}"
        averages = candles[average_column].to_numpy(float)
        starts = times.get_indexer(group.start_timestamp)
        require((starts >= 0).all(), "Episode missing from candles")
        for episode, start in zip(group.itertuples(index=False), starts):
            if not _approach_from_below(start, highs, averages, zone):
                continue
            for policy in POLICIES:
                reclaim, breakout, status, reason = _find_signal(
                    candles, start, average_column, timeframe, policy
                )
                row = {
                    "episode_id": episode.episode_id,
                    "asset": episode.asset,
                    "timeframe": episode.timeframe,
                    "average_type": episode.average_type,
                    "touch_zone": episode.touch_zone,
                    "start_timestamp": episode.start_timestamp,
                    "left_censored": episode.left_censored,
                    "approach": "from_below",
                    "policy": policy,
                    "status": status,
                    "status_reason": reason,
                    "origin_signal_timestamp": episode.start_timestamp + delta,
                    "reclaim_candle_timestamp": times[reclaim] if reclaim is not None else pd.NaT,
                    "reclaim_high": highs[reclaim] if reclaim is not None else np.nan,
                    "breakout_candle_timestamp": times[breakout] if breakout is not None else pd.NaT,
                    "entry_timestamp": times[breakout] + delta if breakout is not None else pd.NaT,
                    "reclaim_delay_minutes": (reclaim - start) * delta.total_seconds() / 60 if reclaim is not None else np.nan,
                    "breakout_delay_minutes": (breakout - reclaim) * delta.total_seconds() / 60 if breakout is not None else np.nan,
                }
                rows.append(row)
    result = pd.DataFrame(rows)
    require(not result.duplicated(["episode_id", "policy"]).any(), "Duplicate candidates")
    return result


def scalar_signal(candles, start, average_type, timeframe, policy):
    """Independent public scalar replay used by validation tests and run audits."""
    return _find_signal(candles.reset_index(drop=True), start, f"average_{average_type}", timeframe, policy)

