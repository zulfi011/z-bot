"""Causal first-touch selection with retrospective episode audit metadata."""

import numpy as np
import pandas as pd

KEYS = ["asset", "timeframe", "average_type", "touch_zone"]
ZONES = {0.5: "0_5", 1.0: "1_0", 1.5: "1_5"}
AVERAGES = ["7d", "15d", "30d"]
RULE = "consecutive_touch_first_v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def build_episodes(candles: pd.DataFrame, events: pd.DataFrame,
                   asset: str, timeframe: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return every-event membership and one audit row per maximal touch run.

    Selection uses current/prior candles only. End, length, and right censoring
    are retrospective metadata and must never be used to select an entry.
    A run starting without a prior valid average is retained but left-censored.
    Missing candle intervals are rejected, not interpreted as non-touches.
    """
    candles = candles.sort_values("open_time").reset_index(drop=True)
    times = pd.DatetimeIndex(candles["open_time"])
    delta = pd.Timedelta(timeframe)
    require(len(times) > 0 and times.tz is not None and str(times.tz) == "UTC",
            "Candles must have nonempty UTC timestamps")
    require(not times.hasnans and times.is_unique, "Invalid/duplicate candle timestamps")
    require(bool((times[1:] - times[:-1] == delta).all()), "Missing/irregular candle interval")
    require(events.event_id.notna().all() and events.event_id.is_unique,
            "Missing/duplicate event IDs")
    require(events.asset.eq(asset).all() and events.timeframe.eq(timeframe).all(),
            "Mixed asset/timeframe input")
    require(not events.duplicated(["timestamp", "average_type", "touch_zone"]).any(),
            "Duplicate classified event")
    require(events.average_type.isin(AVERAGES).all() and events.touch_zone.isin(ZONES).all(),
            "Unsupported event configuration")
    memberships, episodes = [], []
    for average in AVERAGES:
        values = candles[f"average_{average}"]
        valid = values.notna().to_numpy()
        require(bool((values.dropna() > 0).all()), "Nonpositive average")
        for zone, suffix in ZONES.items():
            expected = (values.notna() & candles.high.ge(values * (1 - zone / 100))
                        & candles.low.le(values * (1 + zone / 100))).to_numpy()
            flags = candles[f"touch_{average}_{suffix}"]
            require(flags.notna().all() and flags.isin([True, False]).all(), "Invalid touch flags")
            require(np.array_equal(flags.to_numpy(dtype=bool), expected), "Touch formula mismatch")
            positions = np.flatnonzero(expected)
            source = events.loc[events.average_type.eq(average) & events.touch_zone.eq(zone)]
            source = source.sort_values("timestamp").reset_index(drop=True)
            require(pd.DatetimeIndex(source.timestamp).equals(times[positions]),
                    "Event coverage does not exactly match candle touches")
            for event_col, candle_col in [("price", "close"), ("high", "high"),
                                          ("low", "low"), ("average_value", f"average_{average}")]:
                require(np.array_equal(source[event_col].to_numpy(),
                                       candles.iloc[positions][candle_col].to_numpy()),
                        f"Source event mismatch: {event_col}")
            if not len(positions):
                continue
            starts = np.r_[True, np.diff(positions) != 1]
            group = np.cumsum(starts) - 1
            start_rows = np.flatnonzero(starts)
            end_rows = np.r_[start_rows[1:] - 1, len(positions) - 1]
            first = source.iloc[start_rows].reset_index(drop=True)
            last_positions = positions[end_rows]
            first_positions = positions[start_rows]
            ids = (RULE + ":" + first.event_id).to_numpy()
            left_censored = (first_positions == 0) | ~valid[np.maximum(first_positions - 1, 0)]
            right_censored = ((last_positions == len(candles) - 1)
                              | ~valid[np.minimum(last_positions + 1, len(candles) - 1)])
            membership = source[["event_id", *KEYS, "timestamp"]].copy()
            membership["episode_id"] = ids[group]
            membership["representative_event_id"] = first.event_id.to_numpy()[group]
            membership["retained"] = starts
            membership["reason"] = np.where(starts, "first_touch_of_run", "consecutive_touch")
            memberships.append(membership)
            episode = first[["event_id", *KEYS, "timestamp", "price"]].rename(
                columns={"event_id": "representative_event_id", "timestamp": "start_timestamp"})
            episode["episode_id"] = ids
            episode["signal_available_timestamp"] = times[first_positions] + delta
            episode["end_timestamp"] = times[last_positions]
            episode["touch_candle_count"] = end_rows - start_rows + 1
            episode["duration_minutes"] = episode.touch_candle_count * delta.total_seconds() / 60
            episode["left_censored"] = left_censored
            episode["right_censored"] = right_censored
            episodes.append(episode)
    require(bool(memberships), "No touch events")
    membership = pd.concat(memberships, ignore_index=True).sort_values(
        ["timestamp", "average_type", "touch_zone"]).reset_index(drop=True)
    episode = pd.concat(episodes, ignore_index=True).sort_values(
        ["start_timestamp", "average_type", "touch_zone"]).reset_index(drop=True)
    require(len(membership) == len(events), "Unaccounted source events")
    return membership, episode
