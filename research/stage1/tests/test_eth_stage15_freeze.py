import numpy as np
import pandas as pd

from src.research.eth_stage15_freeze.analysis import (
    block_bootstrap,
    execution_adjusted_return,
    longest_nonpositive_streak,
    simulate_exact_time_stop,
)


def test_execution_costs_are_applied_to_both_sides() -> None:
    result = execution_adjusted_return(pd.Series([0.0]), 10.0, 2.0)[0]
    expected = ((1 - 0.0002) / (1 + 0.0002)) * ((1 - 0.001) / (1 + 0.001)) - 1
    assert np.isclose(result, expected * 100)
    assert result < -0.23


def test_weekly_bootstrap_is_deterministic_and_preserves_dependence_blocks() -> None:
    timestamps = pd.date_range("2024-09-01", periods=70, freq="D", tz="UTC")
    frame = pd.DataFrame({"origin_signal_timestamp": timestamps, "return_pct": np.tile([1.0, -0.2], 35)})
    first = block_bootstrap(frame, "return_pct", repetitions=500, seed=17)
    second = block_bootstrap(frame, "return_pct", repetitions=500, seed=17)
    assert first == second
    assert first["blocks"] == 10
    assert first["ci95_low"] > 0


def test_losing_streak_counts_zero_return_as_nonpositive() -> None:
    assert longest_nonpositive_streak([1, -1, 0, -2, 3, -1]) == 3


def test_exact_stop_uses_adverse_entry_fill_and_gap_open() -> None:
    times = pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC")
    raw = pd.DataFrame({
        "open_time": times,
        "open": [100.0, 95.0, 96.0, 97.0],
        "high": [101.0, 96.0, 97.0, 98.0],
        "low": [99.0, 94.0, 95.0, 96.0],
        "close": [100.0, 95.5, 96.5, 97.5],
    })
    signals = pd.DataFrame({"entry_timestamp": [times[0]], "episode_id": ["e1"]})
    result = simulate_exact_time_stop(signals, raw, 0.0, 10.0, hold_minutes=4, stop_pct=4.0)
    assert np.isclose(result.iloc[0].entry_fill, 100.1)
    assert result.iloc[0].exact_exit_type == "protective_stop"
    assert result.iloc[0].exact_duration_minutes == 2
    assert np.isclose(result.iloc[0].exit_fill, 95.0 * 0.999)
