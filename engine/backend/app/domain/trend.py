"""The trend line used by the Mode A exit: an exponential moving average of 1-minute closes.

Same definition as the research grid (pandas `ewm(span=N, adjust=False)`):

    alpha      = 2 / (N + 1)
    ema[0]     = close[0]
    ema[i]     = alpha * close[i] + (1 - alpha) * ema[i - 1]

It is computed once per completed minute and includes that minute's close, so a lot is compared
against the line it just helped move.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

TWO = Decimal("2")
ONE = Decimal("1")


def alpha(minutes: int) -> Decimal:
    if minutes < 1:
        raise ValueError("EMA length must be at least one minute")
    return TWO / (Decimal(minutes) + ONE)


def advance(previous: Decimal | None, close: Decimal, minutes: int) -> Decimal:
    """One more minute of the EMA. With no previous value the first close seeds it."""
    if previous is None:
        return close
    weight = alpha(minutes)
    return weight * close + (ONE - weight) * previous


def seed(closes: Iterable[Decimal], minutes: int) -> Decimal | None:
    """Warm the EMA up over a run of closes, oldest first."""
    value: Decimal | None = None
    for close in closes:
        value = advance(value, close, minutes)
    return value


def warmup_minutes(minutes: int) -> int:
    """How much history to warm up over: after 20 spans the seed carries under 0.01% of the weight."""
    return minutes * 20
