import numpy as np
import pandas as pd
import pytest

from src.research.stage15_robustness.analysis import (
    block_mean_interval, condition_mask, max_drawdown_pct, period_metrics,
    select_nonoverlap,
)


def frame():
    return pd.DataFrame({
        "episode_id": ["a", "b", "c"],
        "entry_timestamp": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:30", "2025-01-01 01:00"], utc=True),
        "origin_signal_timestamp": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:30", "2025-01-01 01:00"], utc=True),
        "duration": [60., 30., 30.], "outcome": [1., -1., 2.],
        "origin_regime": ["bullish", "bearish", "bullish"],
        "approach": ["from_below", "from_above", "from_below"],
        "average_slope_24h": ["rising", "falling", "rising"],
    })


def test_nonoverlap_keeps_earliest_then_available_entry():
    selected = select_nonoverlap(frame(), "duration")
    assert selected.episode_id.tolist() == ["a", "c"]


def test_nonoverlap_uses_actual_exit_duration():
    data = frame(); data.loc[0, "duration"] = 20
    assert select_nonoverlap(data, "duration").episode_id.tolist() == ["a", "b", "c"]


def test_condition_variants_are_causal_columns():
    data = frame()
    assert condition_mask(data, "all_entries").sum() == 3
    assert condition_mask(data, "bullish_regime").sum() == 2
    assert condition_mask(data, "from_below").sum() == 2
    assert condition_mask(data, "rising_average").sum() == 2
    with pytest.raises(ValueError): condition_mask(data, "future_winner")


def test_period_metrics_apply_cost_after_overlap_filter():
    metrics, selected = period_metrics(frame(), "outcome", "duration")
    assert selected.episode_id.tolist() == ["a", "c"]
    assert metrics["nonoverlap_gross_mean_pct"] == 1.5
    assert metrics["nonoverlap_net_0_2_mean_pct"] == pytest.approx(1.3)
    assert metrics["overlap_removed_pct"] == pytest.approx(100 / 3)


def test_drawdown_compounds_trade_returns():
    value = max_drawdown_pct(pd.Series([10., -10.]))
    assert value == pytest.approx(-10.)


def test_block_interval_is_deterministic_and_cost_adjusted():
    times = pd.date_range("2025-01-01", periods=100, freq="D", tz="UTC")
    data = pd.DataFrame({"origin_signal_timestamp": times, "outcome": np.full(100, 1.)})
    first = block_mean_interval(data, "outcome")
    second = block_mean_interval(data, "outcome")
    assert first == second
    assert first[0] == pytest.approx(.8)
    assert first[1] == pytest.approx(.8)
