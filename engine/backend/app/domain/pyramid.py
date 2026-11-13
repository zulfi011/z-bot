"""The pyramid add-on: adding lots to a trade that is already winning.

A lot bought by any of the three ways in becomes a "parent". While it is open and the market is climbing, the
add-on buys more lots at fixed steps above the parent's fill:

  level 1 at +step%, level 2 at +2 x step%, level 3 at +3 x step% - in order, one lot each
  every add also needs the price to be ABOVE the trend line, so it never adds into a fading move
  adds are skipped inside the strategy's blocked hours, like every other way in

How an add leaves is set per coin, because the coins differ:

  "own"          the add is its own lot: its own stop from its own fill, and always the trend ride.
                 It was bought in a climb, so it is held against the line; if the parent sells first it keeps
                 running. ETH wants this - its money is in long trends.
  "with_parent"  the add has no exit of its own: it is sold the moment its parent is, at the same price, and it
                 parks the PARENT's stop price on Binance. SOL wants this - it exits quickly, and an add that
                 outlives its parent only bleeds.

Same shape as the research (`research/backtests/scripts/eth_pyramid_full.adds_for`), so live adds can be checked
against the backtest: the trigger is a CLOSE at or above the level and above the line, and the buy is the next
minute's open.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PyramidConfig:
    step_pct: Decimal
    maximum_adds: int
    add_exit: str = "own"                    # "own" (its own trend-ride exit) or "with_parent"
    # Shared with the other ways in: the hours the strategy refuses to open lots in.
    blocked_entry_hours: tuple[int, int] | None = None

    def blocked(self, at: datetime) -> bool:
        return bool(self.blocked_entry_hours and self.blocked_entry_hours[0] <= at.hour < self.blocked_entry_hours[1])

    @property
    def follows_parent(self) -> bool:
        return self.add_exit == "with_parent"

    def level_price(self, parent_fill: Decimal, level: int) -> Decimal:
        """The price the `level`-th add needs: the parent's fill plus that many steps."""
        return parent_fill * (HUNDRED + self.step_pct * level) / HUNDRED

    @classmethod
    def from_strategy(cls, strategy: dict) -> "PyramidConfig | None":
        entry = (strategy.get("entry") or {}).get("pyramid_add")
        if not entry:
            return None
        hours = (strategy.get("entry") or {}).get("blocked_entry_hours_utc")
        return cls(step_pct=Decimal(str(entry["step_pct"])), maximum_adds=int(entry["maximum_adds"]),
                   add_exit=str(entry.get("add_exit", "own")),
                   blocked_entry_hours=(hours["start"], hours["end"]) if hours else None)


def wants_add(config: PyramidConfig, parent_fill: Decimal, adds_so_far: int, close: Decimal,
              trend_line: Decimal | None, at: datetime) -> bool:
    """Should a lot be added to this parent on this closed minute?"""
    if adds_so_far >= config.maximum_adds or trend_line is None or config.blocked(at):
        return False
    if close <= trend_line:
        return False                       # never add into a move that has lost its line
    return close >= config.level_price(parent_fill, adds_so_far + 1)
