import numpy as np
import pandas as pd

from experiments.eth_canonical_v1.blocked_hours import _entry_bucket, apply_block
from experiments.eth_canonical_v1.engine import CandidateTrade, MarketData


def test_fixed_block_uses_candidate_entry_hour_only():
    times = pd.date_range("2025-01-01", periods=24, freq="h", tz="UTC")
    market = MarketData(times, np.ones(24), np.ones(24))
    candidates = [CandidateTrade(hour, min(hour + 1, 23), 1.0, "dip", 1, str(hour))
                  for hour in range(24)]
    kept = apply_block(candidates, market, [6, 12])
    assert [candidate.entry for candidate in kept] == [*range(6), *range(12, 24)]
    # An entry before the block remains included even when its exit occurs during it.
    assert candidates[5] in kept


def test_all_hours_does_not_filter_candidates():
    times = pd.date_range("2025-01-01", periods=2, freq="h", tz="UTC")
    market = MarketData(times, np.ones(2), np.ones(2))
    candidates = [CandidateTrade(0, 1, 1.0, "dip", 1, "a")]
    assert apply_block(candidates, market, None) is candidates


def test_entry_bucket_has_four_fixed_utc_sessions():
    assert [_entry_bucket(hour) for hour in (0, 5, 6, 11, 12, 17, 18, 23)] == [
        "00-06", "00-06", "06-12", "06-12", "12-18", "12-18", "18-24", "18-24",
    ]
