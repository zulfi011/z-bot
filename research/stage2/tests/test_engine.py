import pandas as pd
import pytest

from src.backtesting.engine import (
    ChronologicalBacktester,
    FutureDataAccessError,
    Phase,
    StrategyEvent,
)


def sample_candles():
    return pd.DataFrame({
        "open_time": pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC"),
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
    })


class RecordingStrategy:
    def __init__(self):
        self.calls = []

    def on_open(self, event, history):
        self.calls.append(("open", event.index, event.timestamp, history.closed_count,
                           None if history.latest is None else history.latest.open_time))
        return [StrategyEvent("open_seen", {"price": event.price})]

    def on_close(self, event, history):
        self.calls.append(("close", event.index, event.timestamp, history.closed_count,
                           history.latest.open_time))
        return [StrategyEvent("close_seen", {"close": event.candle.close})]


def test_callbacks_are_chronological_and_phase_aware():
    strategy = RecordingStrategy()
    result = ChronologicalBacktester(sample_candles()).run(strategy)

    assert [call[0] for call in strategy.calls] == ["open", "close"] * 3
    assert [call[3] for call in strategy.calls] == [0, 1, 1, 2, 2, 3]
    assert strategy.calls[0][4] is None
    assert strategy.calls[1][4] == pd.Timestamp("2026-01-01 00:00", tz="UTC")
    assert strategy.calls[2][4] == pd.Timestamp("2026-01-01 00:00", tz="UTC")
    assert result.candle_count == result.open_callbacks == result.close_callbacks == 3
    assert [event.sequence for event in result.events] == list(range(6))
    assert [event.phase for event in result.events] == [Phase.OPEN, Phase.CLOSE] * 3


class LookAheadStrategy:
    def on_open(self, event, history):
        history.at(event.timestamp)

    def on_close(self, event, history):
        return None


def test_current_candle_is_hidden_at_its_open():
    with pytest.raises(FutureDataAccessError, match="has not closed"):
        ChronologicalBacktester(sample_candles()).run(LookAheadStrategy())


class CloseAccessStrategy:
    def on_open(self, event, history):
        return None

    def on_close(self, event, history):
        assert history.at(event.candle.open_time) == event.candle


def test_current_candle_is_available_only_at_close():
    result = ChronologicalBacktester(sample_candles()).run(CloseAccessStrategy())
    assert result.close_callbacks == 3


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "unsorted"])
def test_invalid_time_grid_is_rejected(mutation):
    frame = sample_candles()
    if mutation == "gap":
        frame.loc[2, "open_time"] += pd.Timedelta(minutes=1)
    elif mutation == "duplicate":
        frame.loc[1, "open_time"] = frame.loc[0, "open_time"]
    else:
        frame = frame.iloc[::-1]
    with pytest.raises(ValueError, match="timestamps|gap"):
        ChronologicalBacktester(frame)


def test_engine_cannot_be_reused_with_strategy_state():
    engine = ChronologicalBacktester(sample_candles())
    engine.run(RecordingStrategy())
    with pytest.raises(RuntimeError, match="only be run once"):
        engine.run(RecordingStrategy())


def test_naive_timestamps_are_rejected_instead_of_assumed_utc():
    frame = sample_candles()
    frame["open_time"] = frame.open_time.dt.tz_localize(None)
    with pytest.raises(ValueError, match="must use UTC"):
        ChronologicalBacktester(frame)


@pytest.mark.parametrize(
    "column,value",
    [("open", 0.0), ("low", 103.0), ("high", 99.0)],
)
def test_invalid_prices_are_rejected(column, value):
    frame = sample_candles()
    frame.loc[0, column] = value
    with pytest.raises(ValueError, match="prices|OHLC"):
        ChronologicalBacktester(frame)


def test_input_is_copied_and_candles_are_immutable():
    frame = sample_candles()
    engine = ChronologicalBacktester(frame)
    frame.loc[0, "open"] = 999
    strategy = RecordingStrategy()
    result = engine.run(strategy)
    assert result.events[0].details["price"] == 100.0
