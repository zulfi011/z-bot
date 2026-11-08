"""Mode C: buying a break out of a quiet band.

The dip entry needs price to come back down to its average, which in a strong uptrend can take weeks. This
one needs the opposite: a stretch where ETH goes nowhere. When the last `zone_bars` bars of the chart all sit
inside a band no wider than `maximum_zone_pct`, that band is the zone. The first bar to close above its top is
the break; after `confirmation_wait_minutes` the price must still be above the top, and the buy lands on the
next minute's open.

Deliberately the same shape as the research (`run_sol_consolidation_v4.entries_for`), so the live signals can
be checked against the backtest one for one:

  * the zone is measured over the bars BEFORE the breaking bar, never including it
  * only the first break out of each quiet stretch counts, so one long move is one signal
  * the wait is measured in real minutes from the breaking bar's close
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Bar:
    """One bar of the consolidation chart, plus the minute it closed on."""
    open_time: datetime
    high: Decimal
    low: Decimal
    close: Decimal
    last_minute: datetime


@dataclass(frozen=True)
class Zone:
    """The band the price has been stuck in, as it stood before the current bar."""
    top: Decimal
    bottom: Decimal
    width_pct: Decimal
    bars: int
    since: datetime

    @property
    def middle(self) -> Decimal:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True)
class Breakout:
    """A bar that closed above a quiet zone. Not a buy yet - the wait still has to pass."""
    breakout_id: str
    zone: Zone
    broke_at: datetime           # the bar's open time
    confirm_at: datetime         # when the price is checked again
    close: Decimal


@dataclass(frozen=True)
class ConsolidationConfig:
    chart_minutes: int
    zone_bars: int
    maximum_zone_pct: Decimal
    confirmation_wait_minutes: int
    stop_pct: Decimal
    trail_activation_pct: Decimal
    trail_giveback_pct: Decimal
    # Mode C obeys the same closed hours as the dip rule; None means it trades around the clock.
    blocked_entry_hours: tuple[int, int] | None = None

    def blocked(self, at: datetime) -> bool:
        """Is this minute inside the hours the strategy refuses to open lots in?"""
        return bool(self.blocked_entry_hours and self.blocked_entry_hours[0] <= at.hour < self.blocked_entry_hours[1])

    @classmethod
    def from_strategy(cls, strategy: dict) -> "ConsolidationConfig | None":
        entry = (strategy.get("entry") or {}).get("consolidation_breakout")
        if not entry:
            return None
        exit_rules = entry["exit"]
        hours = (strategy.get("entry") or {}).get("blocked_entry_hours_utc")
        return cls(
            chart_minutes=int(entry["chart_minutes"]),
            zone_bars=int(entry["zone_bars"]),
            maximum_zone_pct=Decimal(str(entry["maximum_zone_pct"])),
            confirmation_wait_minutes=int(entry["confirmation_wait_minutes"]),
            stop_pct=Decimal(str(exit_rules["protective_stop_pct_from_entry_fill"])),
            trail_activation_pct=Decimal(str(exit_rules["activation_pct_from_entry_fill"])),
            trail_giveback_pct=Decimal(str(exit_rules["giveback_of_open_profit_pct"])),
            blocked_entry_hours=(hours["start"], hours["end"]) if hours else None,
        )


def build_bars(candles: list, minutes: int) -> list[Bar]:
    """Whole chart bars from 1-minute candles. A bar missing any minute is dropped, never guessed."""
    if minutes < 1:
        raise ValueError("A chart bar must be at least one minute")
    buckets: dict[datetime, list] = {}
    for candle in candles:
        buckets.setdefault(_bucket_start(candle.open_time, minutes), []).append(candle)
    bars = []
    for start in sorted(buckets):
        minutes_in = sorted(buckets[start], key=lambda candle: candle.open_time)
        if len(minutes_in) != minutes:
            continue                                   # a partial or gappy bar tells us nothing
        bars.append(Bar(open_time=start,
                        high=max(candle.high for candle in minutes_in),
                        low=min(candle.low for candle in minutes_in),
                        close=minutes_in[-1].close,
                        last_minute=minutes_in[-1].open_time))
    return bars


def _bucket_start(at: datetime, minutes: int) -> datetime:
    """Which bar a minute belongs to, counted from the epoch so bars never drift."""
    epoch = datetime(1970, 1, 1, tzinfo=at.tzinfo)
    span = timedelta(minutes=minutes)
    return epoch + ((at - epoch) // span) * span


def zone_before(bars: list[Bar], index: int, config: ConsolidationConfig) -> Zone | None:
    """The band formed by the `zone_bars` bars before `index`, or None if there are too few."""
    if index < config.zone_bars:
        return None
    window = bars[index - config.zone_bars:index]
    top = max(bar.high for bar in window)
    bottom = min(bar.low for bar in window)
    if bottom <= 0:
        return None
    width = (top / bottom - 1) * 100
    return Zone(top=top, bottom=bottom, width_pct=width, bars=len(window), since=window[0].open_time)


def current_zone(bars: list[Bar], config: ConsolidationConfig) -> tuple[Zone | None, bool]:
    """The zone as it stands right now, and whether it is quiet enough to trade a break from."""
    zone = zone_before(bars, len(bars), config)
    return zone, bool(zone and zone.width_pct <= config.maximum_zone_pct)


def find_breakouts(bars: list[Bar], config: ConsolidationConfig) -> list[Breakout]:
    """Every first break above a quiet zone, oldest first."""
    breakouts: list[Breakout] = []
    previous_broke = False
    for index, bar in enumerate(bars):
        zone = zone_before(bars, index, config)
        quiet = bool(zone and zone.width_pct <= config.maximum_zone_pct)
        broke = quiet and bar.close > zone.top
        if broke and not previous_broke:
            breakouts.append(Breakout(
                breakout_id=f"consolidation:{bar.open_time.isoformat()}",
                zone=zone, broke_at=bar.open_time, close=bar.close,
                confirm_at=bar.last_minute + timedelta(minutes=config.confirmation_wait_minutes),
            ))
        previous_broke = broke
    return breakouts


def confirm(breakout: Breakout, closes: dict[datetime, Decimal]) -> tuple[str, datetime | None]:
    """What became of a break once its wait ran out.

    ("pending", None)            the wait is still running, or that minute has not been stored yet
    ("failed", None)             price fell back to the zone during the wait, so nothing is bought
    ("confirmed", entry_minute)  buy at that minute's open
    """
    close = closes.get(breakout.confirm_at)
    if close is None:
        return "pending", None
    if close <= breakout.zone.top:
        return "failed", None
    return "confirmed", breakout.confirm_at + timedelta(minutes=1)
