import pandas as pd

from src.backtesting.engine import ChronologicalBacktester
from src.backtesting.entries import (
    EntryReplayStrategy,
    SignalCandle,
    SignalFeed,
    SignalSpec,
    TouchSignalGenerator,
)


START = pd.Timestamp("2026-01-01", tz="UTC")


def bar(minutes, opened, high, low, close, averages=(100.0, 100.0, 100.0)):
    return SignalCandle(
        open_time=START + pd.Timedelta(minutes=minutes),
        open=opened,
        high=high,
        low=low,
        close=close,
        average_7d=averages[0],
        average_15d=averages[1],
        average_30d=averages[2],
    )


def generator(avoid_bearish=False):
    return TouchSignalGenerator(SignalSpec("primary", "3m", avoid_strong_bearish=avoid_bearish))


def test_first_touch_bullish_candle_confirms_at_next_boundary():
    current = generator()
    assert current.process(bar(0, 99, 99.4, 98.5, 99.0)) is None
    signal = current.process(bar(3, 99.5, 100.2, 99.4, 100.0))
    assert signal.status == "confirmed"
    assert signal.start_timestamp == START + pd.Timedelta(minutes=3)
    assert signal.entry_timestamp == START + pd.Timedelta(minutes=6)


def test_first_non_touch_candle_can_confirm_then_episode_is_closed():
    current = generator()
    current.process(bar(0, 99, 99.4, 98.5, 99.0))
    assert current.process(bar(3, 100, 100.2, 99.5, 99.8)) is None
    signal = current.process(bar(6, 101, 102, 100.6, 101.5))
    assert signal.status == "confirmed"


def test_first_non_touch_cancels_when_not_bullish():
    current = generator()
    current.process(bar(0, 99, 99.4, 98.5, 99.0))
    current.process(bar(3, 100, 100.2, 99.5, 99.8))
    cancelled = current.process(bar(6, 102, 102, 100.6, 101))
    assert cancelled.status == "cancelled_at_episode_exit"
    assert cancelled.entry_timestamp is None


def test_confirmation_at_inclusive_30_minute_boundary():
    current = generator()
    current.process(bar(0, 99, 99.4, 98.5, 99.0))
    current.process(bar(3, 100, 100.2, 99.5, 99.8))
    for minute in range(6, 33, 3):
        candle = bar(minute, 100, 100.2, 99.5, 99.8)
        if minute == 33:
            break
        assert current.process(candle) is None
    signal = current.process(bar(33, 99.8, 100.3, 99.5, 100.1))
    assert signal.status == "confirmed"
    assert signal.entry_timestamp == START + pd.Timedelta(minutes=36)


def test_strong_bearish_origin_is_rejected_for_primary():
    current = generator(avoid_bearish=True)
    current.process(bar(0, 98, 99.4, 98, 99))
    assert current.process(bar(3, 99.5, 100.2, 99.4, 100, (99, 100, 101))) is None
    assert current.market_rejections == 1
    assert not current.candidates


def test_signal_fills_at_next_raw_open_with_adverse_slippage():
    raw = pd.DataFrame({
        "open_time": pd.date_range(START, periods=7, freq="1min"),
        "open": [99, 99, 99, 99.5, 99.7, 99.8, 101.0],
        "high": [99.2, 99.2, 99.4, 100.0, 100.1, 100.2, 101.2],
        "low": [98.5, 98.7, 98.8, 99.4, 99.5, 99.6, 100.8],
        "close": [99, 99, 99, 99.7, 99.8, 100.0, 101.1],
    })
    signals = pd.DataFrame({
        "open_time": [START, START + pd.Timedelta(minutes=3)],
        "open": [99.0, 99.5],
        "high": [99.4, 100.2],
        "low": [98.5, 99.4],
        "close": [99.0, 100.0],
        "average_7d": [100.0, 100.0],
        "average_15d": [100.0, 100.0],
        "average_30d": [100.0, 100.0],
    })
    specs = {"primary": SignalSpec("primary", "3m")}
    replay = EntryReplayStrategy({"primary": SignalFeed(signals, "3m")}, specs, 2.0)
    ChronologicalBacktester(raw).run(replay)
    replay.finalize()
    fills = replay.fill_frame()
    assert len(fills) == 1
    assert fills.iloc[0].timestamp == START + pd.Timedelta(minutes=6)
    assert fills.iloc[0].raw_open == 101.0
    assert fills.iloc[0].fill_price == 101.0 * 1.0002

