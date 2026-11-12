"""A phase-aware chronological engine that exposes only causally available bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol

import numpy as np
import pandas as pd


class FutureDataAccessError(IndexError):
    """Raised when a strategy asks for a candle that has not closed yet."""


class Phase(str, Enum):
    OPEN = "open"
    CLOSE = "close"


@dataclass(frozen=True)
class Candle:
    open_time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class OpenEvent:
    index: int
    timestamp: pd.Timestamp
    price: float


@dataclass(frozen=True)
class CloseEvent:
    index: int
    timestamp: pd.Timestamp
    candle: Candle


@dataclass(frozen=True)
class StrategyEvent:
    kind: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    phase: Phase
    timestamp: pd.Timestamp
    candle_index: int
    kind: str
    details: Mapping[str, Any]


@dataclass(frozen=True)
class BacktestResult:
    candle_count: int
    open_callbacks: int
    close_callbacks: int
    started_at: pd.Timestamp
    ended_at: pd.Timestamp
    events: tuple[AuditEvent, ...]


class Strategy(Protocol):
    def on_open(self, event: OpenEvent, history: "HistoryView") -> Iterable[StrategyEvent] | None:
        ...

    def on_close(self, event: CloseEvent, history: "HistoryView") -> Iterable[StrategyEvent] | None:
        ...


class _CandleStore:
    def __init__(self, frame: pd.DataFrame, frequency: str):
        required = ["open_time", "open", "high", "low", "close"]
        missing = [column for column in required if column not in frame]
        if missing:
            raise ValueError(f"Missing candle columns: {missing}")
        if frame.empty:
            raise ValueError("Candle data is empty")

        times = pd.DatetimeIndex(pd.to_datetime(frame.open_time))
        if times.tz is None or str(times.tz) != "UTC":
            raise ValueError("Candle timestamps must use UTC")
        if not times.is_monotonic_increasing or not times.is_unique or times.hasnans:
            raise ValueError("Candle timestamps must be unique and increasing")
        self.frequency = pd.Timedelta(frequency)
        if self.frequency <= pd.Timedelta(0):
            raise ValueError("Frequency must be positive")
        if len(times) > 1 and not bool(((times[1:] - times[:-1]) == self.frequency).all()):
            raise ValueError("Candle timestamps contain a gap or wrong interval")

        prices = frame[["open", "high", "low", "close"]].to_numpy(dtype=float, copy=True)
        if not np.isfinite(prices).all() or not (prices > 0).all():
            raise ValueError("Candle prices must be finite and positive")
        opened, high, low, close = prices.T
        if not ((low <= np.minimum(opened, close)).all()
                and (high >= np.maximum(opened, close)).all()):
            raise ValueError("Invalid OHLC price ordering")
        self.times = times
        self.open = opened
        self.high = high
        self.low = low
        self.close = close

    def __len__(self) -> int:
        return len(self.times)

    def candle(self, index: int) -> Candle:
        return Candle(
            open_time=self.times[index],
            open=float(self.open[index]),
            high=float(self.high[index]),
            low=float(self.low[index]),
            close=float(self.close[index]),
        )


class HistoryView:
    """Read-only access to candles closed by the callback's event time."""

    __slots__ = ("__store", "__visible_through")

    def __init__(self, store: _CandleStore, visible_through: int):
        self.__store = store
        self.__visible_through = visible_through

    @property
    def closed_count(self) -> int:
        return self.__visible_through + 1

    @property
    def latest(self) -> Candle | None:
        if self.__visible_through < 0:
            return None
        return self.__store.candle(self.__visible_through)

    def last(self, count: int) -> tuple[Candle, ...]:
        if count < 1:
            raise ValueError("History length must be positive")
        start = max(0, self.closed_count - count)
        return tuple(self.__store.candle(i) for i in range(start, self.closed_count))

    def at(self, timestamp: pd.Timestamp | str) -> Candle:
        requested = pd.Timestamp(timestamp)
        if requested.tzinfo is None:
            requested = requested.tz_localize("UTC")
        else:
            requested = requested.tz_convert("UTC")
        index = int(self.__store.times.searchsorted(requested))
        if index >= len(self.__store) or self.__store.times[index] != requested:
            beyond_visible_history = (
                self.__visible_through < 0
                or requested > self.__store.times[self.__visible_through]
            )
            if beyond_visible_history:
                raise FutureDataAccessError(f"Candle at {requested} is not available")
            raise KeyError(f"No candle at {requested}")
        if index > self.__visible_through:
            raise FutureDataAccessError(f"Candle at {requested} has not closed")
        return self.__store.candle(index)


class ChronologicalBacktester:
    """Replay open and close events in market-time order exactly once."""

    def __init__(self, candles: pd.DataFrame, frequency: str = "1min"):
        self.__store = _CandleStore(candles, frequency)
        self.__has_run = False

    def run(self, strategy: Strategy) -> BacktestResult:
        if self.__has_run:
            raise RuntimeError("A backtester instance can only be run once")
        self.__has_run = True
        audit: list[AuditEvent] = []
        sequence = 0

        def record(response: Iterable[StrategyEvent] | None, phase: Phase,
                   timestamp: pd.Timestamp, index: int) -> None:
            nonlocal sequence
            if response is None:
                return
            for item in response:
                if not isinstance(item, StrategyEvent):
                    raise TypeError("Strategy callbacks must return StrategyEvent objects")
                audit.append(AuditEvent(
                    sequence=sequence,
                    phase=phase,
                    timestamp=timestamp,
                    candle_index=index,
                    kind=item.kind,
                    details=dict(item.details),
                ))
                sequence += 1

        for index in range(len(self.__store)):
            open_time = self.__store.times[index]
            open_event = OpenEvent(index=index, timestamp=open_time,
                                   price=float(self.__store.open[index]))
            record(strategy.on_open(open_event, HistoryView(self.__store, index - 1)),
                   Phase.OPEN, open_time, index)

            candle = self.__store.candle(index)
            close_time = open_time + self.__store.frequency
            close_event = CloseEvent(index=index, timestamp=close_time, candle=candle)
            record(strategy.on_close(close_event, HistoryView(self.__store, index)),
                   Phase.CLOSE, close_time, index)

        return BacktestResult(
            candle_count=len(self.__store),
            open_callbacks=len(self.__store),
            close_callbacks=len(self.__store),
            started_at=self.__store.times[0],
            ended_at=self.__store.times[-1] + self.__store.frequency,
            events=tuple(audit),
        )
