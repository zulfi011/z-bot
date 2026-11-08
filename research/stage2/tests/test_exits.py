import pandas as pd

from src.backtesting.engine import Candle, ChronologicalBacktester, CloseEvent
from src.backtesting.exits import ExitReplayStrategy, ExitSpec, Position, evaluate_exit


START = pd.Timestamp("2026-01-01", tz="UTC")


def close_event(index, opened, high, low, close):
    candle = Candle(START + pd.Timedelta(minutes=index), opened, high, low, close)
    return CloseEvent(index, candle.open_time + pd.Timedelta(minutes=1), candle)


def trailing_spec(maximum_hold=1_440, slippage=0):
    return ExitSpec("primary", "trailing_after_activation", 4, maximum_hold, slippage,
                    trail_activation_pct=4, trail_giveback_pct=10)


def fixed_spec(maximum_hold=1_440, slippage=0):
    return ExitSpec("control", "fixed_profit_target", 4, maximum_hold, slippage,
                    target_pct=4)


def position(strategy="primary"):
    return Position("signal-1", strategy, START, 100, 100)


def test_trailing_starts_after_activation_candle_and_gives_back_open_profit():
    current = position()
    assert evaluate_exit(current, close_event(0, 100, 104.5, 100, 104), trailing_spec()) is None
    assert current.trailing_active
    trade = evaluate_exit(current, close_event(1, 104.4, 105, 104, 104.2), trailing_spec())
    assert trade.exit_type == "trailing_stop"
    assert trade.raw_exit_price == 104.05
    assert trade.duration_minutes == 2


def test_activation_and_hard_stop_same_candle_uses_stop():
    trade = evaluate_exit(position(), close_event(0, 100, 105, 95, 100), trailing_spec())
    assert trade.exit_type == "ambiguous_stop"
    assert trade.raw_exit_price == 96


def test_fixed_target_and_stop_same_candle_uses_stop():
    trade = evaluate_exit(position("control"), close_event(0, 100, 105, 95, 100), fixed_spec())
    assert trade.exit_type == "ambiguous_stop"
    assert trade.raw_exit_price == 96


def test_favorable_target_gap_uses_open_before_exit_slippage():
    trade = evaluate_exit(position("control"), close_event(0, 105, 106, 104.5, 105), fixed_spec())
    assert trade.exit_type == "profit_target"
    assert trade.raw_exit_price == 105


def test_timeout_uses_close_of_final_allowed_candle():
    current = position("control")
    assert evaluate_exit(current, close_event(0, 100, 101, 99, 100.5), fixed_spec(2)) is None
    trade = evaluate_exit(current, close_event(1, 100.5, 102, 100, 101.5), fixed_spec(2))
    assert trade.exit_type == "time"
    assert trade.raw_exit_price == 101.5
    assert trade.duration_minutes == 2


def test_one_position_ignores_overlap_and_can_reenter_after_exit_boundary():
    raw = pd.DataFrame({
        "open_time": pd.date_range(START, periods=3, freq="1min"),
        "open": [100, 100, 105],
        "high": [101, 105, 106],
        "low": [99, 100, 104],
        "close": [100, 104, 105],
    })
    fills = pd.DataFrame([
        {"signal_id": "a", "strategy": "control", "timestamp": START,
         "raw_open": 100, "fill_price": 100},
        {"signal_id": "b", "strategy": "control", "timestamp": START + pd.Timedelta("1min"),
         "raw_open": 100, "fill_price": 100},
        {"signal_id": "c", "strategy": "control", "timestamp": START + pd.Timedelta("2min"),
         "raw_open": 105, "fill_price": 105},
    ])
    replay = ExitReplayStrategy(fills, {"control": fixed_spec()})
    result = ChronologicalBacktester(raw).run(replay)
    replay.finalize(result.ended_at)
    assert replay.completed_frame().signal_id.tolist() == ["a"]
    assert replay.ignored_frame().signal_id.tolist() == ["b"]
    assert replay.incomplete_frame().signal_id.tolist() == ["c"]


def test_exit_fill_applies_adverse_sell_slippage():
    spec = fixed_spec(slippage=2)
    trade = evaluate_exit(position("control"), close_event(0, 100, 105, 100, 104), spec)
    assert trade.exit_fill == trade.raw_exit_price * 0.9998

