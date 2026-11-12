import numpy as np
import pandas as pd
import pytest

from src.research.stage15_robustness.analysis import select_nonoverlap
from src.research.stage15_v2_execution.simulator import SCENARIOS, SpotExecutionEngine


def raw_frame(periods=1441):
    opened = np.full(periods, 100.)
    return pd.DataFrame({"open_time": pd.date_range("2025-01-01", periods=periods, freq="1min", tz="UTC"),
                         "open": opened, "high": opened + 1, "low": opened - 1, "close": opened})


def test_fee_and_slippage_are_applied_on_both_sides():
    raw = raw_frame(); engine = SpotExecutionEngine(raw)
    result = engine.calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    fee = .001; slip = .0002
    expected = ((100 * (1 - slip)) * (1 - fee) / ((100 * (1 + slip)) * (1 + fee)) - 1) * 100
    assert result.realistic_return_pct == pytest.approx(expected)
    assert result.realistic_entry_fill == pytest.approx(100.02)
    assert result.realistic_exit_fill == pytest.approx(99.98)


def test_slippage_changes_levels_from_actual_entry_fill():
    raw = raw_frame(); raw.loc[2, "high"] = 104.01
    result = SpotExecutionEngine(raw).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert result.gross_exit_type == "profit_target"
    assert result.realistic_exit_type == "time"


def test_same_minute_target_and_stop_uses_stop():
    raw = raw_frame(); raw.loc[4, "high"] = 105; raw.loc[4, "low"] = 95
    result = SpotExecutionEngine(raw).calculate([pd.Timestamp("2025-01-01", tz="UTC")]).iloc[0]
    assert result.gross_exit_type == "ambiguous_stop"
    assert result.gross_return_pct == pytest.approx(-4)


def test_one_position_uses_scenario_specific_exit_time():
    frame = pd.DataFrame({"episode_id": ["a", "b", "c"],
                          "entry_timestamp": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:30",
                                                              "2025-01-01 01:00"], utc=True),
                          "duration": [45., 30., 30.]})
    assert select_nonoverlap(frame, "duration").episode_id.tolist() == ["a", "c"]


def test_scenarios_are_ordered_from_gross_to_severe():
    assert list(SCENARIOS) == ["gross", "fee_only", "realistic", "stressed", "severe"]

