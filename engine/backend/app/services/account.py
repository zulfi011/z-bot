"""The account as the bot sees it: settings, the shared pot, coin switches, the shadow wallet and rounding.

Plain reads and small rules with no trading in them, shared by the trading service, the API and the monitor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.domain.execution import MODULES, CoinAllocation

MONEY = Decimal("0.00000001")
PRICE = Decimal("0.0000000001")
QUANTITY = Decimal("0.000000000001")
ZERO = Decimal("0")
STATE_KEY = "live_execution"
SETTINGS_KEY = "account_settings"
# No money is assumed: the pot is empty and the loss limit off until the user sets them (or sets a shadow amount).
DEFAULT_SETTINGS = {"trading_mode": "shadow", "daily_loss_limit_usd": "0", "maximum_open_value_usd": "0",
                    "pot_lots": 0, "pot_lot_size_usd": "0", "shadow_start_usd": "0"}


@dataclass(frozen=True)
class SharedPot:
    """One set of lots shared by every coin that is switched on, first come first served.

    No coin owns money or slots: any coin's signal buys while one of the `lots` is free and Binance has USDT. The
    last lot takes whatever cash is left after losses (see affordable_lot), and profit refills lots to full size.
    """
    lots: int
    lot_size_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        return self.lot_size_usd * self.lots


def read_pot(connection: Connection) -> SharedPot:
    settings = read_settings(connection)
    return SharedPot(int(settings.get("pot_lots") or 0), Decimal(str(settings.get("pot_lot_size_usd") or "0")))


def suggested_pot(value: Decimal, minimum_lot: Decimal = Decimal("10")) -> SharedPot | None:
    """The growth plan for this much money, for any amount.

    From $300 it is the tested plan: 3 x $100, one more lot per extra $100 up to 5 lots, then +$20 on every lot
    per extra $100 (so $1,000 -> 5 x $200). Below $300: 3 equal lots in whole dollars. None when 3 lots would be
    under the minimum lot size.
    """
    if value < 3 * minimum_lot:
        return None
    if value < 300:
        return SharedPot(3, (value / 3).quantize(Decimal("1"), rounding="ROUND_DOWN"))
    steps = int((value - 300) // 100)
    if steps <= 2:
        return SharedPot(3 + steps, Decimal("100"))
    return SharedPot(5, Decimal(100 + 20 * (steps - 2)))


def open_lot_total(connection: Connection) -> int:
    """Open lots across every coin: they all come out of the one shared pot."""
    return int(connection.execute(text("SELECT count(*) FROM positions WHERE status='open'")).scalar_one())


def affordable_lot(lot: Decimal, free_usdt: Decimal) -> Decimal | None:
    """What one lot spends: the full lot, or - when the pot has less - whatever free USDT is left (cents only).

    Coins share one pot, so the coin that buys last takes what the others left. Binance's own minimum order value
    (about $5) still applies and is checked before the order is sent.
    """
    if free_usdt >= lot:
        return lot
    left = free_usdt.quantize(Decimal("0.01"), rounding="ROUND_DOWN")
    return left if left > 0 else None


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY)


def price(value: Decimal) -> Decimal:
    return value.quantize(PRICE)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY)


def coin_label(symbol: str) -> str:
    return symbol.removesuffix("USDT")


def read_settings(connection: Connection) -> dict:
    value = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:key"), {"key": SETTINGS_KEY}
    ).scalar_one_or_none()
    return {**DEFAULT_SETTINGS, **(value or {})}


def read_allocation(connection: Connection, symbol: str) -> CoinAllocation | None:
    row = connection.execute(
        text("""SELECT dip_enabled, breakout_enabled, pullback_enabled, pyramid_enabled
                FROM coin_allocations WHERE symbol=:symbol"""),
        {"symbol": symbol},
    ).mappings().one_or_none()
    if not row:
        return None
    return CoinAllocation(frozenset(name for name in MODULES if row[f"{name}_enabled"]))




def read_trading_enabled(connection: Connection, symbol: str) -> bool:
    """A coin trades only once it has been switched on; a coin the bot has never seen stays off."""
    value = connection.execute(
        text("SELECT trading_enabled FROM coin_allocations WHERE symbol=:symbol"), {"symbol": symbol}
    ).scalar_one_or_none()
    return value is True


def shadow_account(connection: Connection, settings: dict) -> dict | None:
    """The pretend wallet shadow mode trades with: the starting amount the user set, plus shadow trades' results.

    Only shadow lots count (no Binance order id). None when no starting amount is set: shadow buys are then not
    limited by money, and the dashboard asks for an amount.
    """
    start = Decimal(str(settings.get("shadow_start_usd") or "0"))
    if start <= ZERO:
        return None
    realized = connection.execute(
        text("""SELECT COALESCE(sum(t.net_pnl_usd), 0) FROM trades t
                JOIN positions p ON p.position_id = t.position_id WHERE p.entry_order_id IS NULL""")
    ).scalar_one()
    rows = connection.execute(
        text("SELECT symbol, quantity, allocation_usd FROM positions WHERE status='open' AND entry_order_id IS NULL")
    ).mappings().all()
    open_cost = sum((row["allocation_usd"] for row in rows), ZERO)
    open_value = sum((row["quantity"] * (latest_price(connection, row["symbol"]) or ZERO) for row in rows), ZERO)
    free = start + realized - open_cost
    return {"start": start, "free": free, "open_value": open_value, "open_cost": open_cost, "realized": realized,
            "wallet": free + open_value, "pnl": realized + open_value - open_cost}


def latest_price(connection: Connection, symbol: str, at: datetime | None = None) -> Decimal | None:
    return connection.execute(
        text("""SELECT close FROM candles_1m WHERE symbol=:symbol
                AND (CAST(:at AS timestamptz) IS NULL OR open_time <= CAST(:at AS timestamptz))
                ORDER BY open_time DESC LIMIT 1"""),
        {"symbol": symbol, "at": at},
    ).scalar_one_or_none()
