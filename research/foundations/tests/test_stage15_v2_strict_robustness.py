import numpy as np
import pandas as pd
import pytest

from src.research.stage15_v2_strict.analysis import block_interval, consecutive_losses, filter_mask


def test_consecutive_losses_counts_zero_as_nonwinning():
    assert consecutive_losses([1, -1, 0, -2, 3, -1]) == 3


def test_market_filters_are_causal_existing_columns():
    frame = pd.DataFrame({"origin_regime": ["bullish", "bearish", "missing"],
                          "average_slope_24h": ["rising", "falling", "missing"]})
    assert filter_mask(frame, "all_market_conditions").sum() == 3
    assert filter_mask(frame, "avoid_strong_bearish").tolist() == [True, False, False]
    assert filter_mask(frame, "rising_15d").tolist() == [True, False, False]


def test_block_interval_is_deterministic_and_does_not_double_charge_costs():
    frame = pd.DataFrame({"origin_signal_timestamp": pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC"),
                          "realistic_return_pct": np.full(100, .5)})
    first = block_interval(frame); second = block_interval(frame)
    assert first == second
    assert first[0] == pytest.approx(.5)
    assert first[1] == pytest.approx(.5)

