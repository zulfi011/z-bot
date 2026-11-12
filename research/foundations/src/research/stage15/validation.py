"""Read-only checks independent of the vectorized episode construction."""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from .episodes import KEYS, RULE, require


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_partition(events: pd.DataFrame, membership: pd.DataFrame,
                       episodes: pd.DataFrame, timeframe: str) -> int:
    """Reconstruct maximal runs from source event timestamps, not saved flags."""
    require(membership.event_id.is_unique and episodes.episode_id.is_unique, "Duplicate output IDs")
    require(set(events.event_id) == set(membership.event_id), "Partition loses/adds events")
    require(int(episodes.touch_candle_count.sum()) == len(events), "Run lengths do not reconcile")
    pd.testing.assert_frame_equal(
        events.set_index("event_id")[[*KEYS, "timestamp"]].sort_index(),
        membership.set_index("event_id")[[*KEYS, "timestamp"]].sort_index(), check_exact=True)
    require(membership.retained.sum() == len(episodes), "Not one representative per run")
    require(set(membership.loc[membership.retained, "event_id"])
            == set(episodes.representative_event_id), "Representative IDs mismatch")
    checks = 6
    delta = pd.Timedelta(timeframe)
    audit = episodes.set_index("episode_id")
    mapping = membership.set_index("event_id")
    for _, group in events.groupby(KEYS, sort=True):
        group = group.sort_values("timestamp")
        # This independent timestamp-gap reference operates on original events.
        # The builder separately proves exact event coverage against full candles.
        start = group.timestamp.diff().ne(delta)
        run_ids = (RULE + ":" + group.event_id.where(start)).ffill()
        actual = mapping.loc[group.event_id]
        require(np.array_equal(actual.retained.to_numpy(), start.to_numpy()), "Wrong representative")
        require(np.array_equal(actual.episode_id.to_numpy(), run_ids.to_numpy()), "Wrong membership")
        require(np.array_equal(actual.reason.to_numpy(),
                               np.where(start, "first_touch_of_run", "consecutive_touch")), "Wrong reason")
        require(np.array_equal(actual.representative_event_id.to_numpy(),
                               group.event_id.where(start).ffill().to_numpy()), "Wrong representative link")
        expected = group.assign(_run=run_ids.to_numpy()).groupby("_run").agg(
            start_timestamp=("timestamp", "min"), end_timestamp=("timestamp", "max"),
            touch_candle_count=("event_id", "size"))
        for column in expected:
            require(np.array_equal(expected[column].to_numpy(),
                                   audit.loc[expected.index, column].to_numpy()), f"Wrong {column}")
        require((audit.loc[expected.index, "signal_available_timestamp"]
                 == expected.start_timestamp + delta).all(), "Signal precedes candle completion")
        checks += 8
    return checks


def validate_baseline(baseline: pd.DataFrame, stage1: pd.DataFrame) -> int:
    baseline = baseline.set_index(KEYS).sort_index()
    stage1 = stage1.set_index(KEYS).sort_index()
    require(baseline.index.equals(stage1.index), "Baseline configuration mismatch")
    columns = sorted(set(baseline.columns) & set(stage1.columns))
    require(len(columns) >= 35, "Insufficient Stage 1 cross-check coverage")
    np.testing.assert_allclose(baseline[columns].to_numpy(dtype=float),
                               stage1[columns].to_numpy(dtype=float),
                               rtol=1e-10, atol=1e-10, equal_nan=True)
    return len(columns) * len(baseline)
