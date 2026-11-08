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
    signal_average: Decimal | None
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


class SignalEngine:
    """Pure touch → confirmation state machine for one signal timeframe.

    A touch is a candle whose range overlaps ±zone around the signal average.
    Only the first candle of each consecutive touch run can start an episode.
    The first bullish candle within the wait window confirms it; entry is the
    next signal boundary. Entries inside the blocked UTC hours are skipped, and
    with `require_close_above_30d` a confirmation that closes at or below the
    30-day average is rejected.
    """

    def __init__(
        self,
        strategy_id: str,
        touch_zone_pct: Decimal,
        maximum_wait_minutes: int,
        required_approach: str = "from_below",
        market_filter: str = "avoid_strong_bearish",
        timeframe_minutes: int = 3,
        blocked_entry_hours: tuple[int, int] | None = None,
        require_close_above_30d: bool = False,
        maximum_above_30d_pct: Decimal | None = None,
    ) -> None:
        if timeframe_minutes not in {1, 3, 5}:
            raise ValueError("Unsupported signal timeframe")
        if touch_zone_pct <= 0 or maximum_wait_minutes < 0 or maximum_wait_minutes % timeframe_minutes:
            raise ValueError("Invalid or unaligned signal configuration")
        if required_approach not in {"from_below", "any"}:
            raise ValueError("Unsupported approach rule")
        if market_filter not in {"avoid_strong_bearish", "bullish_only"}:
            raise ValueError("Unsupported market filter")
        self.strategy_id = strategy_id
        self.zone = touch_zone_pct / Decimal("100")
        self.maximum_wait_minutes = maximum_wait_minutes
        self.required_approach = required_approach
        self.market_filter = market_filter
        self.timeframe_minutes = timeframe_minutes
        self.blocked_entry_hours = blocked_entry_hours
        self.require_close_above_30d = require_close_above_30d
        # Optional ceiling for that rule: the confirmation may close at most this % above the 30-day average.
        self.maximum_above_30d = (maximum_above_30d_pct / Decimal("100")) if maximum_above_30d_pct is not None else None
        self.previous: SignalCandle | None = None
        self.previous_touched = False
        self.pending: _PendingEpisode | None = None
        self.episodes_seen = 0
        self.from_below_episodes = 0
        self.market_rejections = 0

    def touched(self, candle: SignalCandle) -> bool:
        average = candle.signal_average
        return bool(
            average is not None
            and candle.high >= average * (Decimal("1") - self.zone)
            and candle.low <= average * (Decimal("1") + self.zone)
        )

    @staticmethod
    def regime(candle: SignalCandle) -> str:
        if candle.average_7d is None or candle.average_15d is None or candle.average_30d is None:
            return "missing"
        if candle.average_7d > candle.average_15d > candle.average_30d:
            return "bullish"
        if candle.average_7d < candle.average_15d < candle.average_30d:
            return "bearish"
        return "neutral"

    def entry_blocked(self, entry_time: datetime) -> bool:
        if not self.blocked_entry_hours:
            return False
        start, end = self.blocked_entry_hours
        return start <= entry_time.hour < end

    def _validate(self, candle: SignalCandle) -> None:
        if candle.open_time.tzinfo is None or candle.open_time.utcoffset() != timedelta(0):
            raise ValueError("Signal candle timestamp must use UTC")
        if candle.open_time.minute % self.timeframe_minutes or candle.open_time.second or candle.open_time.microsecond:
            raise ValueError("Signal candle must align to its UTC timeframe grid")
        if self.previous is not None and candle.open_time != self.previous.open_time + timedelta(minutes=self.timeframe_minutes):
            raise ValueError("Signal candle grid contains a gap")
        if min(candle.open, candle.high, candle.low, candle.close) <= 0:
            raise ValueError("Signal OHLC prices must be positive")
        if candle.low > min(candle.open, candle.close) or candle.high < max(candle.open, candle.close):
            raise ValueError("Signal OHLC values are inconsistent")

    def process(self, candle: SignalCandle) -> SignalTransition:
        self._validate(candle)
        touched = self.touched(candle)
        episode: EpisodeStart | None = None
        resolution: SignalResolution | None = None

        if touched and not self.previous_touched:
            self.episodes_seen += 1
            from_below = False
            if self.previous is not None and self.previous.signal_average is not None:
                lower = self.previous.signal_average * (Decimal("1") - self.zone)
                from_below = self.previous.high < lower
            regime = self.regime(candle)
            status = "observed_not_from_below"
            if from_below:
                self.from_below_episodes += 1
            episode_id = f"{self.strategy_id}:{candle.open_time.isoformat()}"
            if self.required_approach == "any" or from_below:
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
                    self.pending = _PendingEpisode(episode_id, candle.open_time)
            episode = EpisodeStart(
                episode_id=episode_id,
                touch_time=candle.open_time,
                average_value=candle.signal_average,
                regime=regime,
                from_below=from_below,
                status=status,
            )

        if self.pending is not None:
            elapsed = int((candle.open_time - self.pending.start_time).total_seconds() / 60)
            status: str | None = None
            confirmed = elapsed <= self.maximum_wait_minutes and candle.close > candle.open
            entry_time = candle.open_time + timedelta(minutes=self.timeframe_minutes)
            if confirmed:
                if self.entry_blocked(entry_time):
                    status = "skipped_time_window"
                elif self.require_close_above_30d and (candle.average_30d is None or candle.close <= candle.average_30d):
                    status = "rejected_below_30d_average"
                elif (self.maximum_above_30d is not None
                      and candle.close > candle.average_30d * (Decimal("1") + self.maximum_above_30d)):
                    status = "rejected_too_far_above_30d_average"
                else:
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
                    entry_time=entry_time if status == "confirmed" else None,
                    confirmation_close=candle.close if confirmed else None,
                )
                self.pending = None

        self.previous = candle
        self.previous_touched = touched
        return SignalTransition(episode=episode, resolution=resolution)


def build_signal_engine(strategy: dict) -> SignalEngine:
    """Signal engine configured from a schema-v2 strategy document."""
    entry = strategy["entry"]
    hours = entry.get("blocked_entry_hours_utc")
    return SignalEngine(
        strategy["strategy_id"],
        Decimal(str(entry["touch_zone_pct"])),
        int(entry["confirmation"]["maximum_wait_minutes"]),
        entry["approach"],
        entry["market_filter"]["type"],
        int(strategy["market"]["signal_timeframe"].removesuffix("m")),
        (int(hours["start"]), int(hours["end"])) if hours else None,
        (entry.get("trend_filter") or {}).get("type") == "confirmation_close_above_average_30d",
        maximum_above_30d_pct(strategy),
    )


def maximum_above_30d_pct(strategy: dict) -> Decimal | None:
    """The per-coin ceiling on the 30-day trend rule, if the strategy sets one (TRX: 10%)."""
    value = (strategy["entry"].get("trend_filter") or {}).get("maximum_above_average_pct")
    return Decimal(str(value)) if value is not None else None
