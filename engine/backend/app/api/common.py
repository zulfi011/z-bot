"""Shared pieces of the dashboard API: the control-key check, coin names, wallet and price reads."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import text

from app.core import control_session, credentials
from app.core.settings import get_settings
from app.core.strategy import COIN_NAMES, load_strategies, load_strategy
from app.db.session import get_engine
from app.domain.consolidation import ConsolidationConfig
from app.domain.pullback import PullbackConfig
from app.domain.pyramid import PyramidConfig
from app.services import binance_account
from app.services.account import coin_label, read_pot
from app.services.binance_client import BinanceClient

ZERO = Decimal("0")
MAX_AMOUNT = Decimal("1000000")

CHART_INTERVALS = {"1m": ("1 minute", 1), "3m": ("3 minutes", 3), "5m": ("5 minutes", 5),
                   "15m": ("15 minutes", 15), "1h": ("1 hour", 60), "4h": ("4 hours", 240),
                   "1d": ("1 day", 1440)}
EQUITY_PERIOD_DAYS = {"1d": 1, "7d": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365}
LEADERBOARD_PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30}


def _equity_bucket(duration: timedelta, target_points: int = 720) -> str:
    seconds_per_point = max(duration.total_seconds() / target_points, 60)
    for seconds, interval in ((60, "1 minute"), (300, "5 minutes"), (900, "15 minutes"), (3600, "1 hour"),
                              (14400, "4 hours"), (43200, "12 hours"), (86400, "1 day"), (172800, "2 days"),
                              (604800, "7 days")):
        if seconds >= seconds_per_point:
            return interval
    return "30 days"


LOCKED = "This device is locked. Unlock it with your control key."


def _authorize(key: str | None, session: str | None = None) -> None:
    """Open when no control key is set: the app only listens on this computer (127.0.0.1) by default.

    On a server reachable by others, set STRATEGY_EDIT_TOKEN: the dashboard then shows a lock, and every control
    needs an unlocked device (session cookie) or, for scripts, the key in the X-Control-Key header.
    """
    configured = get_settings().strategy_edit_token
    if not configured:
        return
    # Called directly (tests, scripts) the FastAPI parameter defaults are markers, not values.
    key = key if isinstance(key, str) else None
    session = session if isinstance(session, str) else None
    if control_session.expiry(session, configured) or control_session.key_matches(key, configured):
        return
    raise HTTPException(status_code=403, detail=LOCKED)


def _coin_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in load_strategies():
        raise HTTPException(status_code=404, detail="Unknown coin")
    return symbol


def _insert_request(connection, kind: str, amount: Decimal | None = None, position_id: str | None = None,
                    requested_at: datetime | None = None, details: dict | None = None,
                    symbol: str | None = None) -> dict:
    request = {
        "request_id": uuid.uuid4().hex, "kind": kind, "symbol": symbol, "amount_usd": amount,
        "position_id": position_id, "requested_at": requested_at or datetime.now(timezone.utc),
    }
    connection.execute(
        text(
            """
            INSERT INTO control_requests (request_id, kind, symbol, amount_usd, position_id, status, requested_at, details)
            VALUES (:request_id, :kind, :symbol, :amount_usd, :position_id, 'pending', :requested_at, CAST(:details AS jsonb))
            """
        ),
        {**request, "details": json.dumps({**({"symbol": symbol} if symbol else {}), **(details or {})})},
    )
    return {**request, "status": "pending"}


@lru_cache
def _binance_client() -> BinanceClient:
    settings = get_settings()
    return BinanceClient(settings.binance_api_key, settings.binance_api_secret, settings.binance_api_url,
                         settings.binance_recv_window_ms, credentials=credentials.from_file)


def _latest_snapshot(connection) -> dict | None:
    row = connection.execute(text("SELECT * FROM account_snapshots ORDER BY timestamp DESC LIMIT 1")).mappings().one_or_none()
    return dict(row) if row else None


def wallet(force: bool = False) -> dict:
    """Live Binance balances (cached). Used to size lots and to show the money on the dashboard."""
    strategies = load_strategies()
    return binance_account.snapshot(_binance_client(), list(strategies), _prices(list(strategies) + ["BNBUSDT"]),
                                    {symbol: COIN_NAMES.get(symbol, coin_label(symbol)) for symbol in strategies},
                                    force=force)


LATEST_PRICES = text(
    """SELECT s.symbol, c.close FROM unnest(CAST(:symbols AS text[])) AS s(symbol)
       CROSS JOIN LATERAL (SELECT close FROM candles_1m WHERE symbol = s.symbol ORDER BY open_time DESC LIMIT 1) c"""
)


def _prices(symbols: list[str]) -> dict[str, Decimal]:
    """Each coin's latest close: one index lookup per coin. (DISTINCT ON sorted the whole candle table, ~90% of
    every dashboard refresh.)"""
    with get_engine().connect() as connection:
        rows = connection.execute(LATEST_PRICES, {"symbols": symbols}).all()
    return {symbol: close for symbol, close in rows}


def free_usdt(force: bool = False) -> Decimal:
    account = wallet(force)
    return Decimal(str(account.get("usdt", {}).get("free", "0"))) if account.get("connected") else ZERO


def _budget(connection, usdt_free: Decimal) -> dict:
    """The money the coins share: free USDT plus what the real open lots cost, since that comes back as USDT.

    The shared pot (lots x lot size) is measured against it. Shadow lots are left out: they never spent any USDT.
    """
    in_lots = connection.execute(
        text("""SELECT COALESCE(sum(allocation_usd), 0) FROM positions
                WHERE status='open' AND entry_order_id IS NOT NULL""")
    ).scalar_one()
    allocated = read_pot(connection).total_usd
    budget = usdt_free + in_lots
    return {"budget_usd": budget, "in_lots_usd": in_lots, "allocated_usd": allocated, "left_usd": budget - allocated}


@lru_cache(maxsize=None)
def supports(symbol: str) -> dict[str, bool]:
    """Which ways in this coin's strategy actually has."""
    strategy = load_strategy(symbol)
    return {"dip": True, "breakout": ConsolidationConfig.from_strategy(strategy) is not None,
            "pullback": PullbackConfig.from_strategy(strategy) is not None,
            "pyramid": PyramidConfig.from_strategy(strategy) is not None}
