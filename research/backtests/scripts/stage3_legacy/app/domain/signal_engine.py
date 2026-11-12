from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class SignalCandle:
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    average_7d: Decimal | None
    average_15d: Decimal | None
    average_30d: Decimal | None


@dataclass(frozen=True)
class EpisodeStart:
    episode_id: str
    touch_time: datetime
    average_value: Decimal
    regime: str
    from_below: bool
    status: str


@dataclass(frozen=True)
class SignalResolution:
    episode_id: str
    status: str
    confirmation_time: datetime | None
    entry_time: datetime | None
    confirmation_close: Decimal | None


@dataclass(frozen=True)
class SignalTransition:
    episode: EpisodeStart | None = None
    resolution: SignalResolution | None = None


@dataclass
class _PendingEpisode:
    episode_id: str
    start_time: datetime


class FrozenSignalEngine:
    """Pure state machine matching the frozen Stage 2 primary entry rules."""

    def __init__(
        self,
        strategy_id: str,
        touch_zone_pct: Decimal,
        maximum_wait_minutes: int,
        required_approach: str = "from_below",
        market_filter: str = "avoid_strong_bearish",
        timeframe_minutes: int = 3,
        signal_average_days: int = 15,
    ) -> None:
        if timeframe_minutes not in {1, 3, 5}:
            raise ValueError("Unsupported signal timeframe")
        if signal_average_days not in {7, 15, 30}:
            raise ValueError("Unsupported signal average")
        if touch_zone_pct <= 0 or maximum_wait_minutes < 0 or maximum_wait_minutes % timeframe_minutes:
            raise ValueError("Invalid or unaligned frozen signal configuration")
        self.strategy_id = strategy_id
        self.zone = touch_zone_pct / Decimal("100")
        self.maximum_wait_minutes = maximum_wait_minutes
        if required_approach not in {"from_below", "any"}:
            raise ValueError("Unsupported frozen approach rule")
        if market_filter not in {"avoid_strong_bearish", "bullish_only"}:
            raise ValueError("Unsupported frozen market filter")
        self.required_approach = required_approach
        self.market_filter = market_filter
        self.timeframe_minutes = timeframe_minutes
        self.signal_average_days = signal_average_days
        self.previous: SignalCandle | None = None
        self.previous_touched = False
        self.pending: _PendingEpisode | None = None
        self.episodes_seen = 0
        self.from_below_episodes = 0
        self.market_rejections = 0

    def touched(self, candle: SignalCandle) -> bool:
        average = self.signal_average(candle)
        return bool(
            average is not None
            and candle.high >= average * (Decimal("1") - self.zone)
            and candle.low <= average * (Decimal("1") + self.zone)
        )

    def signal_average(self, candle: SignalCandle) -> Decimal | None:
        return getattr(candle, f"average_{self.signal_average_days}d")

    @staticmethod
    def regime(candle: SignalCandle) -> str:
        if candle.average_7d is None or candle.average_15d is None or candle.average_30d is None:
            return "missing"
        if candle.average_7d > candle.average_15d > candle.average_30d:
            return "bullish"
        if candle.average_7d < candle.average_15d < candle.average_30d:
            return "bearish"
        return "neutral"

    def process(self, candle: SignalCandle) -> SignalTransition:
        if candle.open_time.tzinfo is None or candle.open_time.utcoffset() is None:
            raise ValueError("Signal candle timestamp must use UTC")
        if candle.open_time.utcoffset() != timedelta(0):
            raise ValueError("Signal candle timestamp must use UTC")
        if candle.open_time.minute % self.timeframe_minutes or candle.open_time.second or candle.open_time.microsecond:
            raise ValueError("Signal candle must align to its UTC timeframe grid")
        if self.previous is not None and candle.open_time != self.previous.open_time + timedelta(minutes=self.timeframe_minutes):
            raise ValueError("Signal candle grid contains a gap")
        if min(candle.open, candle.high, candle.low, candle.close) <= 0:
            raise ValueError("Signal OHLC prices must be positive")
        if candle.low > min(candle.open, candle.close) or candle.high < max(candle.open, candle.close):
            raise ValueError("Signal OHLC values are inconsistent")
        touched = self.touched(candle)
        episode: EpisodeStart | None = None
        resolution: SignalResolution | None = None

        if touched and not self.previous_touched:
            self.episodes_seen += 1
            from_below = False
            previous_average = self.signal_average(self.previous) if self.previous is not None else None
            if self.previous is not None and previous_average is not None:
                lower = previous_average * (Decimal("1") - self.zone)
                from_below = self.previous.high < lower
            regime = self.regime(candle)
            approach_eligible = self.required_approach == "any" or from_below
            status = "observed_not_from_below"
            if from_below:
                self.from_below_episodes += 1
            if approach_eligible:
                rejected = (
                    regime in {"bearish", "missing"}
                    if self.market_filter == "avoid_strong_bearish"
                    else regime != "bullish"
                )
                if rejected:
                    status = "rejected_market_regime"
                    self.market_rejections += 1
                else:
                    status = "pending_confirmation"
                    episode_id = f"{self.strategy_id}:{candle.open_time.isoformat()}"
                    self.pending = _PendingEpisode(episode_id, candle.open_time)
            episode_id = f"{self.strategy_id}:{candle.open_time.isoformat()}"
            episode = EpisodeStart(
                episode_id=episode_id,
                touch_time=candle.open_time,
                average_value=self.signal_average(candle),
                regime=regime,
                from_below=from_below,
                status=status,
            )

        if self.pending is not None:
            elapsed = int((candle.open_time - self.pending.start_time).total_seconds() / 60)
            status: str | None = None
            confirmed = elapsed <= self.maximum_wait_minutes and candle.close > candle.open
            if confirmed:
                status = "confirmed"
            elif not touched:
                status = "cancelled_at_episode_exit"
            elif elapsed >= self.maximum_wait_minutes:
                status = "expired_wait_limit"
            if status is not None:
                resolution = SignalResolution(
                    episode_id=self.pending.episode_id,
                    status=status,
                    confirmation_time=candle.open_time if confirmed else None,
                    entry_time=candle.open_time + timedelta(minutes=self.timeframe_minutes) if confirmed else None,
                    confirmation_close=candle.close if confirmed else None,
                )
                self.pending = None

        self.previous = candle
        self.previous_touched = touched
        return SignalTransition(episode=episode, resolution=resolution)
