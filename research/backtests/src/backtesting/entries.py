"""Causal touch-entry generation and next-open spot fill simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .engine import CloseEvent, HistoryView, OpenEvent, StrategyEvent


@dataclass(frozen=True)
class SignalSpec:
    name: str
    timeframe: str
    touch_zone_pct: float = 0.5
    maximum_wait_minutes: int = 30
    avoid_strong_bearish: bool = False

    @property
    def duration(self) -> pd.Timedelta:
        return pd.Timedelta(self.timeframe)


@dataclass(frozen=True)
class SignalCandle:
    open_time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    average_7d: float
    average_15d: float
    average_30d: float


@dataclass(frozen=True)
class EntryCandidate:
    signal_id: str
    strategy: str
    timeframe: str
    start_timestamp: pd.Timestamp
    origin_regime: str
    status: str
    confirmation_timestamp: pd.Timestamp | None
    entry_timestamp: pd.Timestamp | None
    confirmation_close: float | None


@dataclass(frozen=True)
class EntryFill:
    signal_id: str
    strategy: str
    timestamp: pd.Timestamp
    raw_open: float
    fill_price: float
    slippage_bps: float


@dataclass
class _PendingEpisode:
    signal_id: str
    start_timestamp: pd.Timestamp
    origin_regime: str


class SignalFeed:
    """Release each precomputed signal candle only at its closing boundary."""

    REQUIRED = [
        "open_time", "open", "high", "low", "close",
        "average_7d", "average_15d", "average_30d",
    ]

    def __init__(self, frame: pd.DataFrame, timeframe: str):
        missing = [column for column in self.REQUIRED if column not in frame]
        if missing:
            raise ValueError(f"Missing signal columns: {missing}")
        times = pd.DatetimeIndex(frame.open_time)
        if times.tz is None or str(times.tz) != "UTC":
            raise ValueError("Signal timestamps must use UTC")
        duration = pd.Timedelta(timeframe)
        if not times.is_unique or not times.is_monotonic_increasing:
            raise ValueError("Signal timestamps must be unique and increasing")
        if len(times) > 1 and not bool(((times[1:] - times[:-1]) == duration).all()):
            raise ValueError("Signal candle grid contains a gap")
        prices = frame[["open", "high", "low", "close"]].to_numpy(float, copy=True)
        if not np.isfinite(prices).all():
            raise ValueError("Signal OHLC contains missing values")
        self._times = times
        self._close_times = times + duration
        self._prices = prices
        self._averages = frame[["average_7d", "average_15d", "average_30d"]].to_numpy(
            float, copy=True
        )
        self._cursor = 0

    def release_at(self, timestamp: pd.Timestamp) -> SignalCandle | None:
        if self._cursor >= len(self._times):
            return None
        expected = self._close_times[self._cursor]
        if expected < timestamp:
            raise RuntimeError("Signal candle was not released chronologically")
        if expected != timestamp:
            return None
        index = self._cursor
        self._cursor += 1
        opened, high, low, close = self._prices[index]
        average_7d, average_15d, average_30d = self._averages[index]
        return SignalCandle(
            open_time=self._times[index],
            open=float(opened),
            high=float(high),
            low=float(low),
            close=float(close),
            average_7d=float(average_7d),
            average_15d=float(average_15d),
            average_30d=float(average_30d),
        )

    @property
    def complete(self) -> bool:
        return self._cursor == len(self._times)


class TouchSignalGenerator:
    """State machine for one deduplicated from-below touch strategy."""

    def __init__(self, spec: SignalSpec):
        if spec.touch_zone_pct <= 0 or spec.maximum_wait_minutes < 0:
            raise ValueError("Invalid signal specification")
        if spec.maximum_wait_minutes % int(spec.duration.total_seconds() / 60):
            raise ValueError("Wait limit must align with signal timeframe")
        self.spec = spec
        self.previous: SignalCandle | None = None
        self.previous_touched = False
        self.pending: _PendingEpisode | None = None
        self.candidates: list[EntryCandidate] = []
        self.episodes_seen = 0
        self.from_below_episodes = 0
        self.market_rejections = 0

    def _touched(self, candle: SignalCandle) -> bool:
        average = candle.average_15d
        if not np.isfinite(average):
            return False
        zone = self.spec.touch_zone_pct / 100
        return candle.high >= average * (1 - zone) and candle.low <= average * (1 + zone)

    @staticmethod
    def _regime(candle: SignalCandle) -> str:
        values = [candle.average_7d, candle.average_15d, candle.average_30d]
        if not np.isfinite(values).all():
            return "missing"
        if candle.average_7d > candle.average_15d > candle.average_30d:
            return "bullish"
        if candle.average_7d < candle.average_15d < candle.average_30d:
            return "bearish"
        return "neutral"

    def _finish(self, status: str, candle: SignalCandle | None = None) -> EntryCandidate:
        if self.pending is None:
            raise RuntimeError("No pending episode")
        confirmed = status == "confirmed"
        candidate = EntryCandidate(
            signal_id=self.pending.signal_id,
            strategy=self.spec.name,
            timeframe=self.spec.timeframe,
            start_timestamp=self.pending.start_timestamp,
            origin_regime=self.pending.origin_regime,
            status=status,
            confirmation_timestamp=candle.open_time if confirmed else None,
            entry_timestamp=(candle.open_time + self.spec.duration) if confirmed else None,
            confirmation_close=candle.close if confirmed else None,
        )
        self.candidates.append(candidate)
        self.pending = None
        return candidate

    def process(self, candle: SignalCandle) -> EntryCandidate | None:
        touched = self._touched(candle)
        new_episode = touched and not self.previous_touched
        produced: EntryCandidate | None = None

        if new_episode:
            self.episodes_seen += 1
            from_below = False
            if self.previous is not None and np.isfinite(self.previous.average_15d):
                lower = self.previous.average_15d * (1 - self.spec.touch_zone_pct / 100)
                from_below = self.previous.high < lower
            if from_below:
                self.from_below_episodes += 1
                regime = self._regime(candle)
                market_allowed = not self.spec.avoid_strong_bearish or regime not in {"bearish", "missing"}
                if market_allowed:
                    signal_id = f"{self.spec.name}:{candle.open_time.isoformat()}"
                    self.pending = _PendingEpisode(signal_id, candle.open_time, regime)
                else:
                    self.market_rejections += 1

        if self.pending is not None:
            elapsed = int((candle.open_time - self.pending.start_timestamp).total_seconds() / 60)
            if elapsed <= self.spec.maximum_wait_minutes and candle.close > candle.open:
                produced = self._finish("confirmed", candle)
            elif not touched:
                produced = self._finish("cancelled_at_episode_exit")
            elif elapsed >= self.spec.maximum_wait_minutes:
                produced = self._finish("expired_wait_limit")

        self.previous = candle
        self.previous_touched = touched
        return produced

    def finalize(self) -> None:
        if self.pending is not None:
            self._finish("truncated_data_end")


class EntryReplayStrategy:
    """Connect signal feeds to raw-minute close events and next-open fills."""

    def __init__(self, feeds: dict[str, SignalFeed], specs: dict[str, SignalSpec],
                 slippage_bps: float = 2.0):
        if feeds.keys() != specs.keys():
            raise ValueError("Feed and specification names differ")
        if slippage_bps < 0:
            raise ValueError("Slippage cannot be negative")
        self.feeds = feeds
        self.generators = {name: TouchSignalGenerator(spec) for name, spec in specs.items()}
        self.slippage_bps = slippage_bps
        self.pending_orders: dict[pd.Timestamp, list[EntryCandidate]] = {}
        self.fills: list[EntryFill] = []

    def on_open(self, event: OpenEvent, history: HistoryView) -> Iterable[StrategyEvent] | None:
        orders = self.pending_orders.pop(event.timestamp, [])
        if not orders:
            return None
        output = []
        for order in orders:
            fill = EntryFill(
                signal_id=order.signal_id,
                strategy=order.strategy,
                timestamp=event.timestamp,
                raw_open=event.price,
                fill_price=event.price * (1 + self.slippage_bps / 10_000),
                slippage_bps=self.slippage_bps,
            )
            self.fills.append(fill)
            output.append(StrategyEvent("entry_fill", asdict(fill)))
        return output

    def on_close(self, event: CloseEvent, history: HistoryView) -> Iterable[StrategyEvent] | None:
        output = []
        for name, feed in self.feeds.items():
            candle = feed.release_at(event.timestamp)
            if candle is None:
                continue
            candidate = self.generators[name].process(candle)
            if candidate is not None and candidate.status == "confirmed":
                self.pending_orders.setdefault(candidate.entry_timestamp, []).append(candidate)
                output.append(StrategyEvent("entry_signal", asdict(candidate)))
        return output or None

    def finalize(self) -> None:
        for generator in self.generators.values():
            generator.finalize()
        if self.pending_orders:
            raise RuntimeError("Confirmed orders remain after the raw candle history")
        if not all(feed.complete for feed in self.feeds.values()):
            raise RuntimeError("Not every signal candle was released")

    def candidate_frame(self) -> pd.DataFrame:
        rows = [asdict(candidate) for generator in self.generators.values()
                for candidate in generator.candidates]
        return pd.DataFrame(rows)

    def fill_frame(self) -> pd.DataFrame:
        return pd.DataFrame(asdict(fill) for fill in self.fills)

