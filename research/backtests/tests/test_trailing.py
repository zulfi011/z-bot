import pandas as pd

from src.backtesting.trailing import simulate_fixed, simulate_trailing


def candles(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_activation_candle_cannot_trigger_trail():
    path = candles([
        (100, 104.5, 100, 104),
        (104, 105, 103, 104),
    ])
    result = simulate_trailing(path, activation_pct=4, giveback_pct=25)
    assert result.exit_type == "trailing_stop"
    assert result.duration_minutes == 2


def test_stop_wins_activation_conflict():
    path = candles([(100, 105, 95, 100)])
    result = simulate_trailing(path, activation_pct=4, giveback_pct=20)
    assert result.exit_type == "ambiguous_stop"


def test_trail_uses_prior_peak_and_adverse_gap_fill():
    path = candles([
        (100, 104.5, 100, 104),
        (101, 106, 100, 102),
    ])
    result = simulate_trailing(path, activation_pct=4, giveback_pct=20)
    assert result.exit_type == "trailing_stop"
    assert result.raw_exit == 101


def test_fixed_target_and_stop_conflict_uses_stop():
    path = candles([(100, 105, 95, 100)])
    result = simulate_fixed(path)
    assert result.exit_type == "ambiguous_stop"

