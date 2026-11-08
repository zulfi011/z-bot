from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


ONE_MINUTE = timedelta(minutes=1)


@dataclass(frozen=True)
class Candle:
    symbol: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    source: str
    source_event_time: datetime | None = None

    def validate(self, now: datetime | None = None) -> None:
        current_time = now or datetime.now(timezone.utc)
        if self.source_event_time is not None:
            current_time = max(current_time, self.source_event_time)
        if self.open_time.tzinfo is None or self.close_time.tzinfo is None:
            raise ValueError("Candle timestamps must be timezone-aware")
        if self.open_time.second or self.open_time.microsecond:
            raise ValueError("One-minute candle open time must align to a minute")
        if self.close_time != self.open_time + ONE_MINUTE - timedelta(milliseconds=1):
            raise ValueError("Candle close time does not match a one-minute interval")
        if self.close_time >= current_time:
            raise ValueError("Open candle cannot be persisted")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.high < self.low:
            raise ValueError("High price cannot be below low price")
        if self.volume < 0 or self.quote_volume < 0 or self.trade_count < 0:
            raise ValueError("Volume and trade count cannot be negative")


def utc_from_milliseconds(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
