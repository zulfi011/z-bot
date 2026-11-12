"""Behavioral tests for the isolated Stage 1.5 first-touch rule."""

import numpy as np
import pandas as pd
import pytest

from src.research.stage15.episodes import AVERAGES, ZONES, build_episodes
from src.research.stage15.validation import validate_partition


def fixture(prices, averages=None):
    times = pd.date_range("2025-01-01 23:50", periods=len(prices), freq="5min", tz="UTC")
    candles = pd.DataFrame({"open_time": times, "high": prices, "low": prices, "close": prices})
    rows = []
    for average in AVERAGES:
        values = np.full(len(prices), 100.) if averages is None else np.array(averages)
        candles[f"average_{average}"] = values
        for zone, suffix in ZONES.items():
            touched = (candles.high >= values * (1-zone/100)) & (candles.low <= values * (1+zone/100))
            candles[f"touch_{average}_{suffix}"] = touched
            for i in np.flatnonzero(touched):
                rows.append({"event_id": f"event_{i}_{average}_{zone}", "asset": "TEST",
                    "timeframe": "5m", "average_type": average, "touch_zone": zone,
                    "timestamp": times[i], "price": prices[i], "high": prices[i], "low": prices[i],
                    "average_value": values[i]})
    events = pd.DataFrame(rows)
    return candles, events


def primary(frame):
    return frame.loc[frame.average_type.eq("15d") & frame.touch_zone.eq(.5)].reset_index(drop=True)


def test_runs_reset_and_exact_membership():
    candles, events = fixture([105., 100., 100., 105., 100., 105.])
    mapping, episodes = build_episodes(candles, events, "TEST", "5m")
    assert primary(mapping).retained.tolist() == [True, False, True]
    assert primary(episodes).touch_candle_count.tolist() == [2, 1]
    assert not episodes.left_censored.any()
    assert not episodes.right_censored.any()
    assert validate_partition(events, mapping, episodes, "5m") > 0


def test_nested_zones_keep_separate_run_boundaries():
    candles, events = fixture([105., 101., 100., 101., 105.])
    _, episodes = build_episodes(candles, events, "TEST", "5m")
    narrow = primary(episodes).iloc[0]
    wide = episodes.loc[episodes.average_type.eq("15d") & episodes.touch_zone.eq(1.)].iloc[0]
    assert narrow.touch_candle_count == 1
    assert wide.touch_candle_count == 3
    assert narrow.start_timestamp > wide.start_timestamp


def test_midnight_and_average_change_do_not_reset_touch():
    candles, events = fixture([105., 100., 100.4, 105.], [100., 100., 100.4, 100.4])
    _, episodes = build_episodes(candles, events, "TEST", "5m")
    assert primary(episodes).touch_candle_count.tolist() == [2]


def test_boundary_and_warmup_censoring():
    candles, events = fixture([100., 100., 100.], [np.nan, 100., 100.])
    _, episodes = build_episodes(candles, events, "TEST", "5m")
    assert episodes.left_censored.all()
    assert episodes.right_censored.all()
    assert episodes.touch_candle_count.eq(2).all()


def test_unknown_average_ends_run_with_censoring():
    candles, events = fixture([100., 100., 100.], [100., np.nan, 100.])
    _, episodes = build_episodes(candles, events, "TEST", "5m")
    assert primary(episodes).touch_candle_count.tolist() == [1, 1]
    assert episodes.left_censored.all() and episodes.right_censored.all()


def test_missing_candles_rejected():
    candles, events = fixture([100., 100., 100.])
    with pytest.raises(ValueError, match="interval"):
        build_episodes(candles.drop(index=1), events, "TEST", "5m")


def test_duplicate_event_rejected():
    candles, events = fixture([100., 105.])
    with pytest.raises(ValueError, match="event IDs"):
        build_episodes(candles, pd.concat([events, events.iloc[:1]]), "TEST", "5m")


def test_missing_event_rejected():
    candles, events = fixture([100., 105.])
    with pytest.raises(ValueError, match="coverage"):
        build_episodes(candles, events.iloc[1:], "TEST", "5m")


def test_corrupt_touch_flag_rejected():
    candles, events = fixture([100., 105.])
    candles.loc[0, "touch_15d_0_5"] = False
    with pytest.raises(ValueError, match="formula"):
        build_episodes(candles, events, "TEST", "5m")


def test_corrupt_event_price_rejected():
    candles, events = fixture([100., 105.])
    events.loc[0, "price"] = 999.
    with pytest.raises(ValueError, match="price"):
        build_episodes(candles, events, "TEST", "5m")


def test_future_data_does_not_change_past_selection():
    candles, events = fixture([105., 100., 100., 100., 105., 100.])
    full, _ = build_episodes(candles, events, "TEST", "5m")
    past, _ = build_episodes(candles.iloc[:3], events.loc[events.timestamp <= candles.open_time.iloc[2]], "TEST", "5m")
    pd.testing.assert_frame_equal(past, full.loc[full.timestamp <= candles.open_time.iloc[2]].reset_index(drop=True))


def test_shuffled_input_is_deterministic_and_does_not_mutate():
    candles, events = fixture([105., 100., 100., 105., 100.])
    copy_c, copy_e = candles.copy(deep=True), events.copy(deep=True)
    a, b = build_episodes(candles, events, "TEST", "5m")
    c, d = build_episodes(candles.sample(frac=1, random_state=1), events.sample(frac=1, random_state=2), "TEST", "5m")
    pd.testing.assert_frame_equal(a, c)
    pd.testing.assert_frame_equal(b, d)
    pd.testing.assert_frame_equal(candles, copy_c)
    pd.testing.assert_frame_equal(events, copy_e)


def test_reference_validation_detects_tampering():
    candles, events = fixture([105., 100., 100., 105.])
    mapping, episodes = build_episodes(candles, events, "TEST", "5m")
    mapping.loc[mapping.retained, "retained"] = False
    with pytest.raises(ValueError, match="representative"):
        validate_partition(events, mapping, episodes, "5m")


def test_metrics_keep_unknown_ambiguous_and_conditional_denominators():
    from src.research.stage15.metrics import required_columns, summarize, TARGETS, STOPS, TRAILS, WINDOWS
    frame = pd.DataFrame({column: [np.nan] * 5 for column in required_columns()})
    frame["observation_complete_24h"] = [True, True, True, True, False]
    frame["trailing_activation_reached"] = [True, True, True, True, False]
    for target in TARGETS:
        frame[f"reached_{target}_pct"] = pd.array([True, False, True, False, pd.NA], dtype="boolean")
        frame[f"time_to_{target}_pct_minutes"] = [1., np.nan, 3., np.nan, np.nan]
    for window in WINDOWS:
        for side in ["downside", "upside"]:
            frame[f"{side}_window_complete_{window}"] = [True, True, True, True, False]
            frame[f"max_{side}_{window}_pct"] = [-2., -1., -3., -2., 999.] if side == "downside" else [1., 2., 3., 2., 999.]
        frame[f"post_activation_window_complete_{window}"] = [True, True, True, False, False]
        frame[f"extra_upside_after_activation_{window}_pct"] = [1., 2., 3., 999., 999.]
    for stop in STOPS:
        frame[f"target_2_5_vs_stop_{stop}_outcome"] = ["target_first", "stop_first", "same_candle_ambiguous", "neither", "incomplete_unknown"]
    for trail in TRAILS:
        frame[f"trail_{trail}_outcome"] = ["triggered_resolved", "ambiguous_same_candle", "not_triggered_24h", "incomplete_unknown", "not_activated"]
        frame[f"trail_{trail}_old_locked_profit_pct"] = [2., 999., 999., 999., 999.]
    result = summarize(frame)
    assert result["reach_probability_pct"] == 50.
    assert result["target_2_5_unknown_count"] == 1
    assert result["target_2_5_first_vs_stop_2_5_pct"] == 25.
    assert result["first_2_5_target_first_decisive_pct"] == 50.
    assert result["trail30_resolved_pct"] == pytest.approx(100/3)
    assert result["trail30_median_realized_return_pct"] == 2.
    assert result["mae_24h_median_pct"] == -2.
    assert result["mfe_24h_median_pct"] == 2.
    assert result["post_activation_median_extra_upside_24h_pct"] == 2.
    assert np.isnan(result["return_24h_median_pct"])
