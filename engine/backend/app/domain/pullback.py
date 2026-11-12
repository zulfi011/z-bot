"""The pullback entry: buying the end of a short dip inside an uptrend.

The dip entry needs price to come back to its 7-day average, and the quiet-band breakout needs a quiet band. In a strong uptrend
neither happens: the price runs far above the average in a wide range, and the core sits idle. This third way in
buys the pauses of that climb instead:

  * the uptrend: the daily 7-, 15- and 30-day averages stacked upward, as they stand for that UTC day
  * the pullback: 1-minute closes BELOW an N-hour EMA of 1-minute closes, for at least `dwell_minutes` in a row
  * the signal: the first close back ABOVE the line ends the pullback; the buy lands on the next minute's open

Deliberately the same shape as the research (`stage2_backtesting/scripts/eth_pullback.pullback_entries`), so the
live signals can be checked against the backtest one for one:

  * the EMA is pandas `ewm(span=N, adjust=False)` and includes the minute's own close (see `trend`)
  * "below" is strictly `close < line`; a close equal to the line ends the pullback
  * the dwell is the run of consecutive below-minutes ending at the minute BEFORE the reclaim

The live feed can miss minutes; research data never does. A missing minute ends the run rather than bridging it,
so a gap can only ever cost a signal, never invent one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain import trend

ONE_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class PullbackConfig:
    ema_minutes: int
    dwell_minutes: int
    requires_uptrend: bool = True
    # Shared with the dip rule: the hours the strategy refuses to open lots in, checked on the buy minute.
    blocked_entry_hours: tuple[int, int] | None = None

    def blocked(self, at: datetime) -> bool:
        return bool(self.blocked_entry_hours and self.blocked_entry_hours[0] <= at.hour < self.blocked_entry_hours[1])

    @classmethod
    def from_strategy(cls, strategy: dict) -> "PullbackConfig | None":
        entry = (strategy.get("entry") or {}).get("pullback_to_trend")
        if not entry:
            return None
        hours = (strategy.get("entry") or {}).get("blocked_entry_hours_utc")
        return cls(ema_minutes=int(entry["ema_minutes"]), dwell_minutes=int(entry["dwell_minutes"]),
                   requires_uptrend=bool(entry.get("requires_uptrend", True)),
                   blocked_entry_hours=(hours["start"], hours["end"]) if hours else None)


@dataclass(frozen=True)
class PullbackState:
    """Everything the rule remembers between minutes. Small enough to store after every pass."""
    ema: Decimal | None = None
    at: datetime | None = None              # the minute `ema` includes
    below_since: datetime | None = None     # first minute of the current run below the line
    below_minutes: int = 0                  # consecutive minutes below the line, ending at `at`

    def to_json(self) -> dict:
        return {"ema": None if self.ema is None else str(self.ema),
                "at": None if self.at is None else self.at.isoformat(),
                "below_since": None if self.below_since is None else self.below_since.isoformat(),
                "below_minutes": self.below_minutes}

    @classmethod
    def from_json(cls, value: dict | None) -> "PullbackState":
        value = value or {}
        return cls(ema=Decimal(value["ema"]) if value.get("ema") is not None else None,
                   at=datetime.fromisoformat(value["at"]) if value.get("at") else None,
                   below_since=datetime.fromisoformat(value["below_since"]) if value.get("below_since") else None,
                   below_minutes=int(value.get("below_minutes") or 0))


@dataclass(frozen=True)
class Reclaim:
    """A pullback that ended with a close back above the line. Not yet a buy: the uptrend and hours decide."""
    pullback_id: str
    below_since: datetime
    below_minutes: int
    reclaim_at: datetime        # the minute whose close came back above the line
    close: Decimal
    line: Decimal

    @property
    def entry_at(self) -> datetime:
        return self.reclaim_at + ONE_MINUTE


def step(state: PullbackState, open_time: datetime, close: Decimal,
         config: PullbackConfig) -> tuple[PullbackState, Reclaim | None]:
    """Advance the rule by one closed minute."""
    gap = state.at is not None and open_time != state.at + ONE_MINUTE
    run, since = (0, None) if gap else (state.below_minutes, state.below_since)
    line = trend.advance(state.ema, close, config.ema_minutes)
    if close < line:
        return PullbackState(line, open_time, since or open_time, run + 1), None
    reclaim = None
    if run >= config.dwell_minutes and since is not None:
        reclaim = Reclaim(pullback_id=f"pullback:{open_time.isoformat()}", below_since=since, below_minutes=run,
                          reclaim_at=open_time, close=close, line=line)
    return PullbackState(line, open_time, None, 0), reclaim


def replay(candles, config: PullbackConfig, state: PullbackState | None = None) -> tuple[PullbackState, list[Reclaim]]:
    """Run a sequence of (open_time, close) minutes through the rule, oldest first."""
    state = state or PullbackState()
    found: list[Reclaim] = []
    for open_time, close in candles:
        state, reclaim = step(state, open_time, Decimal(close), config)
        if reclaim:
            found.append(reclaim)
    return state, found


def warmup_minutes(config: PullbackConfig) -> int:
    """History to warm the line up over; long enough that no real pullback run is cut short either."""
    return trend.warmup_minutes(config.ema_minutes)

