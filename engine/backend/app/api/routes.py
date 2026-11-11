"""Read model and account controls for the multi-coin live-trading dashboard."""

from __future__ import annotations

import csv
import io
import json
import re
import uuid
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Request, Response
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core import credentials
from app.core import control_session
from app.domain import trend
from app.domain.consolidation import ConsolidationConfig, build_bars, current_zone, zone_before
from app.domain.pullback import PullbackConfig, PullbackState, step as pullback_step
from app.domain.pyramid import PyramidConfig
from app.core.settings import get_settings
from app.core.strategy import COIN_NAMES, load_strategies, load_strategy
from app.db.session import get_engine
from app.domain.execution import (
    MODULES, CoinAllocation, ExecutionConfig, ExitSignal, FeeContext,
    Position, fill_exit,
)
from app.services import binance_account, binance_reachability
from app.services.binance_client import BinanceClient, BinanceError
from app.services.monitoring_service import bnb_round_trip_usd
from app.services.live_execution_service import (
    SETTINGS_KEY, affordable_lot, coin_label, open_lot_total, read_allocation, read_pot, read_settings,
    read_trading_enabled, shadow_account, suggested_pot,
)


router = APIRouter(prefix="/api/v1")
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


# ------------------------------------------------------------------ controls
class TradingModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["off", "shadow", "live"]
    daily_loss_limit_usd: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)
    maximum_open_value_usd: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)


class MoneySettingsRequest(BaseModel):
    """Limits and the shadow wallet's starting amount. 0 switches a limit off; any field left out is kept."""
    model_config = ConfigDict(extra="forbid")
    daily_loss_limit_usd: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT, decimal_places=2)
    maximum_open_value_usd: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT, decimal_places=2)
    shadow_start_usd: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT, decimal_places=2)


class TradingSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    close_positions: bool = False


class ModuleRequest(BaseModel):
    """An extra way in is simply on or off - it always shares the coin's lots."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class PotRequest(BaseModel):
    """The shared pot: how many lots all coins share, and how much each lot spends."""
    model_config = ConfigDict(extra="forbid")
    lot_size_usd: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)
    lots: int = Field(ge=1, le=50)


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


class UnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=500)


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _secure_cookie(request: Request) -> bool:
    """HTTPS in front (Tailscale) means a Secure cookie; plain http on localhost for development does not."""
    origin = request.headers.get("origin", "")
    return (origin.startswith("https://") or request.headers.get("x-forwarded-proto") == "https"
            or request.url.scheme == "https" or request.url.hostname not in ("localhost", "127.0.0.1"))


@router.get("/session")
def session_status(session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    configured = get_settings().strategy_edit_token
    expires = control_session.expiry(session, configured) if isinstance(session, str) else None
    return {"unlocked": expires is not None, "controls_enabled": bool(configured),
            "expires_at": datetime.fromtimestamp(expires, timezone.utc) if expires else None}


@router.post("/session")
def unlock(body: UnlockRequest, request: Request, response: Response) -> dict:
    """Trade the control key for a 30-day session cookie on this device."""
    configured = get_settings().strategy_edit_token
    if not configured:
        raise HTTPException(status_code=503, detail="Controls are disabled until STRATEGY_EDIT_TOKEN is set on the server")
    address = _client_address(request)
    wait = control_session.blocked_for(address)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many wrong keys. Try again in {max(1, wait // 60)} minute(s).")
    if not control_session.key_matches(body.key.strip(), configured):
        control_session.record_failure(address)
        raise HTTPException(status_code=403, detail="That is not the control key.")
    control_session.clear_failures(address)
    token, expires = control_session.issue(configured)
    response.set_cookie(control_session.COOKIE, token, max_age=control_session.LIFETIME_SECONDS, httponly=True,
                        secure=_secure_cookie(request), samesite="strict", path="/api")
    return {"unlocked": True, "expires_at": datetime.fromtimestamp(expires, timezone.utc)}


@router.delete("/session")
def lock(request: Request, response: Response) -> dict:
    response.delete_cookie(control_session.COOKIE, path="/api", httponly=True, secure=_secure_cookie(request),
                           samesite="strict")
    return {"unlocked": False}


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


@router.post("/lots/{symbol}/buy-now", status_code=202)
def buy_now(symbol: str, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    _authorize(key, session)
    symbol = _coin_symbol(symbol)
    label = coin_label(symbol)
    with get_engine().begin() as connection:
        pending = connection.execute(
            text("SELECT count(*) FROM control_requests WHERE status='pending' AND kind='manual_buy' AND symbol=:symbol"),
            {"symbol": symbol},
        ).scalar_one()
        if pending:
            raise HTTPException(status_code=409, detail=f"A {label} buy-now request is already waiting")
        if not read_trading_enabled(connection, symbol):
            raise HTTPException(status_code=409, detail=f"{label} is switched off — switch it on first")
        pot = read_pot(connection)
        if open_lot_total(connection) >= pot.lots:
            raise HTTPException(status_code=409, detail=f"All {pot.lots} shared lots are open.")
        settings = read_settings(connection)
        if settings.get("trading_mode") == "live":
            usdt, where = free_usdt(force=True), "Binance"
        else:
            # Shadow buys spend the shadow wallet (or are not limited by money until a starting amount is set),
            # exactly as the engine decides them.
            shadow = shadow_account(connection, settings)
            usdt, where = (shadow["free"], "The shadow wallet") if shadow else (pot.lot_size_usd, "")
        if affordable_lot(pot.lot_size_usd, usdt) is None:
            raise HTTPException(status_code=409, detail=f"{where} has ${usdt:.2f} free USDT, nothing left to buy with.")
        return _insert_request(connection, "manual_buy", symbol=symbol)


@router.put("/pot", status_code=202)
def set_pot(body: PotRequest, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    """Set the shared pot: lots x lot size, used by every coin that is switched on. Open lots keep their size."""
    _authorize(key, session)
    first = next(iter(load_strategies().values()))["portfolio"]
    minimum, maximum = Decimal(str(first["minimum_lot_size_usd"])), Decimal(str(first["maximum_lot_size_usd"]))
    if not minimum <= body.lot_size_usd <= maximum:
        raise HTTPException(status_code=422, detail=f"A lot must be between ${minimum:.0f} and ${maximum:.0f}.")
    # Set by hand: from now on the pot no longer follows the growth plan when the starting amount changes.
    changes = {"pot_lots": body.lots, "pot_lot_size_usd": str(body.lot_size_usd), "pot_set_by_user": True}
    with get_engine().begin() as connection:
        connection.execute(
            text("""INSERT INTO engine_state (key, value, updated_at) VALUES (:key, CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO UPDATE SET value = engine_state.value || EXCLUDED.value, updated_at=now()"""),
            {"key": SETTINGS_KEY, "value": json.dumps(changes)},
        )
        connection.execute(
            text("""INSERT INTO system_events (level, component, event_type, details)
                    VALUES ('INFO','allocation','shared_pot_set', CAST(:d AS jsonb))"""),
            {"d": json.dumps(changes)},
        )
        open_lots = open_lot_total(connection)
    return {"status": "applied", "lots": body.lots, "lot_size_usd": body.lot_size_usd, "open_lots": open_lots}


@router.put("/coins/{symbol}/entries/{module}", status_code=202)
def set_entry_module(symbol: str, module: str, body: ModuleRequest,
                     key: str | None = Header(default=None, alias="X-Control-Key"),
                     session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    """Switch one way in on or off. Every way in shares the pot's lots; there are no reserved lots."""
    _authorize(key, session)
    symbol = _coin_symbol(symbol)
    if module not in MODULES:
        raise HTTPException(status_code=404, detail=f"Unknown way in: {module}")
    if body.enabled and not supports(symbol)[module]:
        raise HTTPException(status_code=422,
                            detail=f"{coin_label(symbol)}'s strategy has no {module} entry, so it cannot be switched on.")
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('allocation'))"))
        stored = read_allocation(connection, symbol) or CoinAllocation.default(load_strategy(symbol))
        entries = set(stored.entries)
        entries.add(module) if body.enabled else entries.discard(module)
        target = CoinAllocation(frozenset(entries))
        _save_allocation(connection, symbol, target, event="coin_entry_module_set",
                         extra={"module": module, "enabled": body.enabled})
    return {"status": "applied", "symbol": symbol, "module": module, "enabled": body.enabled}


def _save_allocation(connection, symbol: str, target: CoinAllocation, event: str = "coin_allocation_set",
                     extra: dict | None = None) -> None:
    """The coin's row: its on/off switch and extra-entry toggles. A row created here starts switched off."""
    connection.execute(
        text(
            """
            INSERT INTO coin_allocations (symbol, dip_enabled, breakout_enabled, pullback_enabled,
                                          pyramid_enabled, trading_enabled, revision, request_id, updated_at)
            VALUES (:symbol, :dip, :breakout, :pullback, :pyramid, false, 1, NULL, now())
            ON CONFLICT (symbol) DO UPDATE SET dip_enabled=EXCLUDED.dip_enabled, breakout_enabled=EXCLUDED.breakout_enabled,
                pullback_enabled=EXCLUDED.pullback_enabled, pyramid_enabled=EXCLUDED.pyramid_enabled,
                revision=coin_allocations.revision + 1, updated_at=now()
            """
        ),
        {"symbol": symbol,
         "dip": target.enabled("dip"), "breakout": target.enabled("breakout"),
         "pullback": target.enabled("pullback"), "pyramid": target.enabled("pyramid")},
    )
    connection.execute(
        text("""INSERT INTO system_events (level, component, event_type, details)
                VALUES ('INFO','allocation',:event, CAST(:d AS jsonb))"""),
        {"event": event, "d": json.dumps({"symbol": symbol, **(extra or {})})},
    )


@router.put("/coins/{symbol}/trading", status_code=202)
def set_trading(symbol: str, body: TradingSwitchRequest,
                key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    """Switch one coin on or off for the shared pot, straight away. Off can also close its open lots."""
    _authorize(key, session)
    symbol = _coin_symbol(symbol)
    label = coin_label(symbol)
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('allocation'))"))
        if read_allocation(connection, symbol) is None:
            _save_allocation(connection, symbol, CoinAllocation.default(load_strategy(symbol)), event="coin_added")
        connection.execute(
            text("UPDATE coin_allocations SET trading_enabled=:on, updated_at=now() WHERE symbol=:symbol"),
            {"on": body.enabled, "symbol": symbol},
        )
        connection.execute(
            text("""INSERT INTO system_events (level, component, event_type, details)
                    VALUES ('INFO','allocation',:event, CAST(:d AS jsonb))"""),
            {"event": "coin_switched_on" if body.enabled else "coin_switched_off",
             "d": json.dumps({"symbol": symbol, "close_positions": body.close_positions})},
        )
        result: dict = {"status": "applied", "symbol": symbol, "enabled": body.enabled}
        if not body.enabled and body.close_positions:
            now = datetime.now(timezone.utc)
            closes = []
            for position_id in connection.execute(
                text("""SELECT p.position_id FROM positions p WHERE p.symbol=:symbol AND p.status='open'
                        AND NOT EXISTS (SELECT 1 FROM control_requests r WHERE r.status='pending'
                                        AND r.kind='close_position' AND r.position_id=p.position_id)
                        ORDER BY p.entry_time FOR UPDATE OF p"""),
                {"symbol": symbol},
            ).scalars():
                closes.append(_insert_request(connection, "close_position", position_id=position_id, symbol=symbol,
                                              requested_at=now, details={"reason": f"{label} switched off"}))
            result["closes"] = closes
        return result


@router.put("/settings/trading", status_code=202)
def set_trading_mode(body: TradingModeRequest, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    """off = nothing opens or is bought, shadow = decisions are recorded but no orders are sent, live = real orders."""
    _authorize(key, session)
    if body.mode == "live" and not credentials.attached():
        raise HTTPException(status_code=409, detail="Attach your Binance account before switching to Live.")
    changes = {"trading_mode": body.mode}
    if body.daily_loss_limit_usd is not None:
        changes["daily_loss_limit_usd"] = str(body.daily_loss_limit_usd)
    if body.maximum_open_value_usd is not None:
        changes["maximum_open_value_usd"] = str(body.maximum_open_value_usd)
    with get_engine().begin() as connection:
        connection.execute(
            text("""INSERT INTO engine_state (key, value, updated_at) VALUES (:key, CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO UPDATE SET value = engine_state.value || EXCLUDED.value, updated_at=now()"""),
            {"key": SETTINGS_KEY, "value": json.dumps(changes)},
        )
        connection.execute(
            text("""INSERT INTO system_events (level, component, event_type, details)
                    VALUES ('WARNING','settings','trading_mode_changed', CAST(:d AS jsonb))"""),
            {"d": json.dumps(changes)},
        )
        return read_settings(connection)


@router.put("/settings/money")
def set_money_settings(body: MoneySettingsRequest, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    _authorize(key, session)
    changes: dict = {name: str(value) for name, value in body.model_dump(exclude_none=True).items()}
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    with get_engine().begin() as connection:
        # Until the user sets the pot by hand, it follows the growth plan for the shadow starting amount.
        if body.shadow_start_usd and not read_settings(connection).get("pot_set_by_user"):
            minimum = Decimal(str(next(iter(load_strategies().values()))["portfolio"]["minimum_lot_size_usd"]))
            plan = suggested_pot(body.shadow_start_usd, minimum)
            if plan:
                changes.update(pot_lots=plan.lots, pot_lot_size_usd=str(plan.lot_size_usd))
        connection.execute(
            text("""INSERT INTO engine_state (key, value, updated_at) VALUES (:key, CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO UPDATE SET value = engine_state.value || EXCLUDED.value, updated_at=now()"""),
            {"key": SETTINGS_KEY, "value": json.dumps(changes)},
        )
        connection.execute(
            text("""INSERT INTO system_events (level, component, event_type, details)
                    VALUES ('INFO','settings','money_settings_changed', CAST(:d AS jsonb))"""),
            {"d": json.dumps(changes)},
        )
        return read_settings(connection)


@router.post("/positions/{position_id}/close", status_code=202)
def close_position(position_id: str, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    _authorize(key, session)
    with get_engine().begin() as connection:
        position = connection.execute(
            text("SELECT status, symbol FROM positions WHERE position_id=:id FOR UPDATE"), {"id": position_id}
        ).mappings().one_or_none()
        if position is None:
            raise HTTPException(status_code=404, detail="Position not found")
        if position["status"] != "open":
            return {"status": "closed", "position_id": position_id}
        pending = connection.execute(
            text("SELECT request_id FROM control_requests WHERE status='pending' AND kind='close_position' AND position_id=:id"),
            {"id": position_id},
        ).scalar_one_or_none()
        if pending:
            return {"status": "pending", "request_id": pending, "position_id": position_id}
        return _insert_request(connection, "close_position", position_id=position_id, symbol=position["symbol"])


@router.post("/requests/{request_id}/cancel")
def cancel_request(request_id: str, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    _authorize(key, session)
    with get_engine().begin() as connection:
        updated = connection.execute(
            text(
                """
                UPDATE control_requests SET status='rejected', reason='Cancelled by you', processed_at=now()
                WHERE request_id=:id AND status='pending' RETURNING request_id
                """
            ),
            {"id": request_id},
        ).scalar_one_or_none()
    if not updated:
        raise HTTPException(status_code=409, detail="Only waiting requests can be cancelled")
    return {"status": "cancelled", "request_id": request_id}


# ------------------------------------------------------------------- reads
@router.get("/health/live")
def liveness() -> dict:
    return {"status": "ok", "service": "api", "version": get_settings().app_version}


@router.get("/health/ready")
def readiness() -> dict:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            mode = str(read_settings(connection).get("trading_mode", "shadow"))
        strategies = load_strategies()
    except (SQLAlchemyError, OSError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail="Application is not ready") from error
    return {"status": "ready", "services": {"api": "ok", "database": "ok", "strategy_config": "ok"},
            "strategies": {symbol: strategy["strategy_id"] for symbol, strategy in strategies.items()},
            "trading_mode": mode}


@lru_cache
def _binance_client() -> BinanceClient:
    settings = get_settings()
    return BinanceClient(settings.binance_api_key, settings.binance_api_secret, settings.binance_api_url,
                         settings.binance_recv_window_ms, credentials=credentials.from_file)


class CredentialsRequest(BaseModel):
    # Checked in the handler, not here: a validation error would echo the submitted secret back.
    model_config = ConfigDict(extra="forbid")
    api_key: str
    api_secret: str


KEY_FORMAT = re.compile(r"[A-Za-z0-9]{16,128}")


def _credentials_view() -> dict:
    found = credentials.current()
    return {"attached": found is not None, "source": credentials.source(),
            "key_hint": credentials.hint(found[0]) if found else None}


@router.get("/binance/credentials")
def credentials_status() -> dict:
    """Whether a Binance key is attached, and where from. The secret is never returned; the key only as a hint."""
    return _credentials_view()


@router.post("/binance/credentials")
def attach_credentials(body: CredentialsRequest, key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    """Check the key with Binance, refuse one that can withdraw, then keep it on this machine."""
    _authorize(key, session)
    if not (KEY_FORMAT.fullmatch(body.api_key.strip()) and KEY_FORMAT.fullmatch(body.api_secret.strip())):
        raise HTTPException(status_code=400, detail="A Binance API key and secret are 16 to 128 letters and numbers. "
                                                    "Copy them again from Binance.")
    settings = get_settings()
    candidate = BinanceClient(body.api_key, body.api_secret, settings.binance_api_url, settings.binance_recv_window_ms)
    try:
        account = candidate.signed_get("/api/v3/account", {"omitZeroBalances": "true"})
    except BinanceError as error:
        raise HTTPException(status_code=400, detail=f"Binance refused this key: {error.explanation}") from error
    try:
        restrictions = candidate.signed_get("/sapi/v1/account/apiRestrictions") or {}
    except BinanceError:
        restrictions = {}
    if restrictions.get("enableWithdrawals"):
        raise HTTPException(status_code=400, detail="This key can withdraw money. Z-Bot never needs that: edit the key on "
                                                    "Binance, untick \"Enable Withdrawals\" and attach it again.")
    if account.get("canTrade") is False or restrictions.get("enableSpotAndMarginTrading") is False:
        raise HTTPException(status_code=400, detail="This key cannot trade. Edit it on Binance and tick "
                                                    "\"Enable Spot & Margin Trading\".")
    credentials.save(body.api_key, body.api_secret)
    binance_account.forget()
    return _credentials_view()


@router.delete("/binance/credentials")
def detach_credentials(key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    _authorize(key, session)
    with get_engine().begin() as connection:
        if str(read_settings(connection).get("trading_mode", "shadow")) == "live":
            raise HTTPException(status_code=409, detail="Switch to Shadow before removing the key.")
    credentials.remove()
    binance_account.forget()
    return _credentials_view()


@router.get("/binance/account")
def binance_account_view(key: str | None = Header(default=None, alias="X-Control-Key"),
            session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    """Real Binance balances and the API key's safety checklist. Read-only; needs the control key."""
    _authorize(key, session)
    strategies = load_strategies()
    symbols = list(strategies)
    prices = _prices(symbols + ["BNBUSDT"])
    names = {symbol: COIN_NAMES.get(symbol, coin_label(symbol)) for symbol in symbols}
    return binance_account.snapshot(_binance_client(), symbols, prices, names)


@router.get("/binance/reachability")
def binance_reachability_check() -> dict:
    """Whether Binance's trading API accepts requests from this server (cached for 5 minutes, no API key used)."""
    return binance_reachability.check()


@router.get("/strategy")
def strategy_documents() -> dict:
    return load_strategies()


@router.get("/strategy/{symbol}")
def strategy_document(symbol: str) -> dict:
    return load_strategy(_coin_symbol(symbol))


def _close_estimate(row: dict, config: ExecutionConfig, context: FeeContext, mark: Decimal, now: datetime) -> dict:
    """What closing this lot right now would return, after exit slippage and fee."""
    position = Position(row["position_id"], row["entry_time"], row["raw_entry_price"], row["entry_fill_price"],
                        row["quantity"], row["allocation_usd"], row["entry_fee_usd"], row["entry_fee_asset"],
                        symbol=row["symbol"])
    fill = fill_exit(position, ExitSignal("manual_close", mark, now, 0), config, context)
    return {"price": mark, "exit_fill_price": fill.fill_price, "fee_usd": fill.fee.usd, "fee_asset": fill.fee.asset,
            "slippage_usd": fill.slippage_usd, "cash_back_usd": fill.cash_in_usd, "net_pnl_usd": fill.net_pnl_usd,
            "net_return_pct": fill.net_return_pct}


def _position_view(row: dict, config: ExecutionConfig, mark: Decimal | None,
                   context: FeeContext | None = None, now: datetime | None = None) -> dict:
    fill = row["entry_fill_price"]
    # The stop parked on Binance, as stored when it was placed (rounded to the price tick); the formula is only a
    # fallback for a lot whose stop order could not be placed.
    stop = row.get("stop_price") or fill * (1 - config.stop_pct / 100)
    activation = fill * (1 + config.trail_activation_pct / 100)
    peak = row["peak_price"] or fill
    trend_ride = bool(row.get("trend_exit_active")) and config.trend_exit_ema_minutes is not None
    # A trend-ride lot has no giveback level: it is held until a minute closes below the trend line.
    trail = (fill + (peak - fill) * (1 - config.trail_giveback_pct / 100)
             if row["trailing_active"] and not trend_ride else None)
    value = row["quantity"] * mark if mark else None
    cost = row["allocation_usd"] + (row["entry_fee_usd"] if row["entry_fee_asset"] == "BNB" else ZERO)
    return {
        **row, "coin": coin_label(row["symbol"]), "current_price": mark, "market_value_usd": value,
        "unrealized_pnl_usd": value - cost if value is not None else None,
        "unrealized_pct": (value / cost - 1) * 100 if value is not None and cost else None,
        "stop_price": stop, "activation_price": activation, "trail_price": trail,
        "exit_mode": "trend" if trend_ride else "giveback",
        "trend_exit_pending": bool(row.get("trend_exit_pending")),
        "trend_ema_minutes": config.trend_exit_ema_minutes if trend_ride else None,
        "stop_pct": config.stop_pct, "trail_activation_pct": config.trail_activation_pct,
        "trail_giveback_pct": config.trail_giveback_pct,
        "distance_to_stop_pct": (mark / stop - 1) * 100 if mark else None,
        "distance_to_activation_pct": (activation / mark - 1) * 100 if mark and not row["trailing_active"] else None,
        "activation_progress_pct": max(ZERO, min(Decimal("100"), (mark - fill) / (activation - fill) * 100))
        if mark and not row["trailing_active"] else Decimal("100"),
        "close_estimate": _close_estimate(row, config, context, mark, now) if mark and context and now else None,
    }


def _trend_line(connection, symbol: str, chart: list[dict], ema_minutes: int, bucket_minutes: int) -> None:
    """Add the trend line to each chart bucket, as the value at the bucket's last minute.

    The EMA is defined on 1-minute closes, so it is rebuilt here from the raw candles with a warm-up in front
    of the visible range. Slow charts are skipped: a 16-hour line on a 1-day chart says nothing, and reading
    months of minutes would make the dashboard crawl.
    """
    if not chart or bucket_minutes > 60:
        return
    warmup = ema_minutes * 5
    rows = connection.execute(
        text("""SELECT open_time, close FROM candles_1m
                WHERE symbol=:s AND open_time >= :start - make_interval(mins => :warmup)
                ORDER BY open_time"""),
        {"s": symbol, "start": chart[0]["open_time"], "warmup": warmup},
    ).all()
    if not rows:
        return
    span = timedelta(minutes=bucket_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    by_bucket: dict[datetime, Decimal] = {}
    value = None
    for open_time, close in rows:
        value = trend.advance(value, Decimal(close), ema_minutes)
        bucket = epoch + ((open_time - epoch) // span) * span
        by_bucket[bucket] = value
    for row in chart:
        row["trend_line"] = by_bucket.get(row["open_time"])


class _RawCandle:
    __slots__ = ("open_time", "high", "low", "close")

    def __init__(self, open_time, high, low, close):
        self.open_time, self.high, self.low, self.close = open_time, high, low, close


def _consolidation_band(connection, symbol: str, chart: list[dict], rule: ConsolidationConfig,
                        bucket_minutes: int) -> None:
    """Mark every chart bucket that sat inside a quiet band, so the zone can be drawn where it happened.

    The band is the one the rule was watching at that moment: the `zone_bars` bars before the current one. A
    bucket gets no band when the price was not quiet then, which is what makes the shading meaningful.
    """
    if not chart:
        return
    warmup = rule.chart_minutes * (rule.zone_bars + 1)
    rows = connection.execute(
        text("""SELECT open_time, high, low, close FROM candles_1m
                WHERE symbol=:s AND open_time >= :start - make_interval(mins => :warmup)
                ORDER BY open_time"""),
        {"s": symbol, "start": chart[0]["open_time"], "warmup": warmup},
    ).all()
    bars = build_bars([_RawCandle(*row) for row in rows], rule.chart_minutes)
    span = timedelta(minutes=rule.chart_minutes)
    bands = {}
    for index, bar in enumerate(bars):
        zone = zone_before(bars, index, rule)
        if zone and zone.width_pct <= rule.maximum_zone_pct:
            bands[bar.open_time] = zone
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    for row in chart:
        bar_start = epoch + ((row["open_time"] - epoch) // span) * span
        zone = bands.get(bar_start)
        row["zone_top"] = zone.top if zone else None
        row["zone_bottom"] = zone.bottom if zone else None


def _consolidation_view(connection, symbol: str, strategy_id: str, rule: ConsolidationConfig | None,
                        mark) -> dict | None:
    """The quiet-band breakout right now: the band being watched, how quiet it is, and any break waiting out its confirmation."""
    if rule is None:
        return None
    stored = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:key"), {"key": f"consolidation:{symbol}"}
    ).scalar_one_or_none() or {}
    pending = connection.execute(
        text("""SELECT signal_id, signal_time, details FROM signals
                WHERE strategy_id=:strategy AND status='pending_confirmation'
                  AND details->>'kind'='consolidation'
                ORDER BY signal_time DESC LIMIT 1"""),
        {"strategy": strategy_id},
    ).mappings().one_or_none()
    top = Decimal(stored["zone_top"]) if stored.get("zone_top") else None
    bottom = Decimal(stored["zone_bottom"]) if stored.get("zone_bottom") else None
    width = Decimal(stored["zone_width_pct"]) if stored.get("zone_width_pct") else None
    quiet = bool(stored.get("quiet"))
    return {
        "chart_minutes": rule.chart_minutes, "zone_bars": rule.zone_bars,
        "zone_hours": rule.chart_minutes * rule.zone_bars / 60,
        "maximum_zone_pct": rule.maximum_zone_pct, "confirmation_wait_minutes": rule.confirmation_wait_minutes,
        # The breakout's own exit numbers: on AAVE the dip now arms later than a break does, so the page says both.
        "stop_pct": rule.stop_pct, "trail_activation_pct": rule.trail_activation_pct,
        "trail_giveback_pct": rule.trail_giveback_pct,
        "quiet": quiet, "zone_top": top, "zone_bottom": bottom, "zone_width_pct": width,
        "zone_since": stored.get("zone_since"),
        # How far the band still has to tighten before a break from it would be traded.
        "width_needed_pct": None if width is None else max(ZERO, width - rule.maximum_zone_pct),
        "distance_to_break_pct": None if (top is None or not mark) else (top / mark - 1) * 100,
        "state": ("breaking" if quiet and top is not None and mark and mark > top
                  else "quiet" if quiet else "too_wide" if width is not None else "warming_up"),
        "pending_break": None if pending is None else {
            "signal_id": pending["signal_id"], "broke_at": pending["signal_time"],
            "confirm_at": pending["details"].get("confirm_at"),
            "zone_top": Decimal(pending["details"]["zone_top"]) if pending["details"].get("zone_top") else None,
        },
        "checked_at": stored.get("checked_at"), "breakouts_seen": stored.get("breakouts_seen"),
    }


def _day_regimes(connection, symbol: str, start: datetime) -> dict[datetime, str]:
    """The trend for every UTC day from `start`, as the daily averages effective that day define it."""
    rows = connection.execute(
        text("""SELECT effective_at, average_7d, average_15d, average_30d FROM daily_averages
                WHERE symbol=:s AND effective_at >= date_trunc('day', CAST(:start AS timestamptz))"""),
        {"s": symbol, "start": start},
    ).all()
    regimes = {}
    for day, a7, a15, a30 in rows:
        regimes[day] = (None if None in (a7, a15, a30) else
                        "bullish" if a7 > a15 > a30 else "bearish" if a7 < a15 < a30 else "neutral")
    return regimes


def _pullback_overlay(connection, symbol: str, chart: list[dict], rule: PullbackConfig, bucket_minutes: int) -> None:
    """The pullback line on each bucket, and whether a pullback was armed there.

    "Armed" means the rule would buy the next close above the line: inside an uptrend, and already below it for
    the full dwell. That is the stretch worth seeing on the chart - where the third way in was loaded. It is
    rebuilt from 1-minute candles with the same `step` the live rule uses, after a 5-span warm-up. Daily charts
    are skipped: a 24-hour line on 1-day candles would read months of minutes to say nothing.
    """
    if not chart or bucket_minutes > 240:
        return
    warmup = rule.ema_minutes * 5
    rows = connection.execute(
        text("""SELECT open_time, close FROM candles_1m
                WHERE symbol=:s AND open_time >= :start - make_interval(mins => :warmup)
                ORDER BY open_time"""),
        {"s": symbol, "start": chart[0]["open_time"], "warmup": warmup},
    ).all()
    if not rows:
        return
    regimes = _day_regimes(connection, symbol, chart[0]["open_time"])
    span = timedelta(minutes=bucket_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    lines: dict[datetime, Decimal] = {}
    armed: set[datetime] = set()
    state = PullbackState()
    for open_time, close in rows:
        state, _ = pullback_step(state, open_time, Decimal(close), rule)
        bucket = epoch + ((open_time - epoch) // span) * span
        lines[bucket] = state.ema
        day = open_time.replace(hour=0, minute=0, second=0, microsecond=0)
        if state.below_minutes >= rule.dwell_minutes and (not rule.requires_uptrend or regimes.get(day) == "bullish"):
            armed.add(bucket)
    for row in chart:
        row["pullback_line"] = lines.get(row["open_time"])
        row["pullback_armed"] = row["open_time"] in armed


def _pullback_view(connection, symbol: str, strategy_id: str, rule: PullbackConfig | None, mark,
                   regime: str) -> dict | None:
    """The pullback entry right now: the line, how long price has been under it, and what would happen next."""
    if rule is None:
        return None
    stored = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:key"), {"key": f"pullback:{symbol}"}
    ).scalar_one_or_none() or {}
    line = Decimal(stored["line"]) if stored.get("line") else None
    below = int(stored.get("below_minutes") or 0)
    uptrend = regime == "bullish" or not rule.requires_uptrend
    last_signal = connection.execute(
        text("""SELECT signal_id, signal_time, status, entry_time, details FROM signals
                WHERE strategy_id=:strategy AND details->>'kind'='pullback'
                ORDER BY signal_time DESC LIMIT 1"""),
        {"strategy": strategy_id},
    ).mappings().one_or_none()
    state = ("warming_up" if line is None else "no_uptrend" if not uptrend
             else "armed" if below >= rule.dwell_minutes else "dipping" if below > 0 else "above")
    return {
        "ema_minutes": rule.ema_minutes, "ema_hours": rule.ema_minutes / 60, "dwell_minutes": rule.dwell_minutes,
        "requires_uptrend": rule.requires_uptrend, "uptrend": uptrend,
        "line": line, "line_at": stored.get("line_at"),
        "below_since": stored.get("below_since"), "below_minutes": below,
        "minutes_to_arm": max(0, rule.dwell_minutes - below) if below else rule.dwell_minutes,
        "distance_to_line_pct": None if (line is None or not mark) else (mark / line - 1) * 100,
        "state": state,
        "last_signal": None if last_signal is None else {
            "signal_id": last_signal["signal_id"], "at": last_signal["signal_time"], "status": last_signal["status"],
            "entry_time": last_signal["entry_time"],
            "below_minutes": (last_signal["details"] or {}).get("below_minutes"),
        },
        "activation_at": stored.get("activation_at"), "checked_at": stored.get("checked_at"),
    }


def _pyramid_view(connection, symbol: str, rule: PyramidConfig | None, allocation: CoinAllocation,
                  positions: list[dict], mark, trend_line) -> dict | None:
    """The pyramid add-on right now: its lots, and what each open lot needs before another is added."""
    if rule is None:
        return None
    counts = dict(connection.execute(
        text("""SELECT parent_position_id, count(*) FROM positions
                WHERE symbol=:s AND parent_position_id IS NOT NULL GROUP BY 1"""),
        {"s": symbol},
    ).all())
    parents = []
    for row in sorted(positions, key=lambda item: item["entry_time"]):
        if row["entry_source"] == "pyramid":
            continue
        adds = int(counts.get(row["position_id"], 0))
        left = rule.maximum_adds - adds
        next_price = (row["entry_fill_price"] * (100 + rule.step_pct * (adds + 1)) / 100) if left > 0 else None
        parents.append({
            "position_id": row["position_id"], "lot_number": row["lot_number"], "source": row["entry_source"],
            "entry_fill_price": row["entry_fill_price"], "adds": adds, "adds_left": left,
            "next_add_price": next_price,
            "distance_to_add_pct": None if (next_price is None or not mark) else (next_price / mark - 1) * 100,
            "above_line": None if (trend_line is None or not mark) else mark > trend_line,
        })
    return {"step_pct": rule.step_pct, "maximum_adds": rule.maximum_adds, "add_exit": rule.add_exit,
            "blocked_entry_hours": list(rule.blocked_entry_hours) if rule.blocked_entry_hours else None,
            "enabled": allocation.enabled("pyramid"), "parents": parents,
            "adds_open": sum(1 for row in positions if row["entry_source"] == "pyramid"),
            "adds_total": sum(counts.values())}


def _trade_stats(connection, symbol: str | None) -> dict:
    stats = dict(connection.execute(
        text(
            """
            SELECT count(*) AS trades,
                   count(*) FILTER (WHERE net_pnl_usd > 0) AS wins,
                   count(*) FILTER (WHERE net_pnl_usd < 0) AS losses,
                   COALESCE(sum(net_pnl_usd) FILTER (WHERE net_pnl_usd > 0), 0) AS gross_win_usd,
                   COALESCE(-sum(net_pnl_usd) FILTER (WHERE net_pnl_usd < 0), 0) AS gross_loss_usd,
                   avg(net_return_pct) FILTER (WHERE net_pnl_usd > 0) AS average_win_pct,
                   avg(net_return_pct) FILTER (WHERE net_pnl_usd < 0) AS average_loss_pct,
                   max(net_return_pct) AS best_pct, min(net_return_pct) AS worst_pct,
                   avg(duration_minutes) AS average_hold_minutes,
                   count(*) FILTER (WHERE exit_reason='trailing_stop') AS trailing_exits,
                   count(*) FILTER (WHERE exit_reason IN ('protective_stop','ambiguous_stop')) AS stop_exits,
                   count(*) FILTER (WHERE exit_reason='manual_close') AS manual_exits,
                   COALESCE(sum(net_pnl_usd) FILTER (WHERE exit_time >= date_trunc('day', now())), 0) AS today_pnl_usd,
                   min(entry_time) AS first_entry,
                   COALESCE(sum(net_pnl_usd), 0) AS realized_usd,
                   COALESCE(sum(entry_fee_usd + exit_fee_usd), 0) AS fees_usd,
                   COALESCE(sum(slippage_usd), 0) AS slippage_usd
            FROM trades WHERE CAST(:symbol AS text) IS NULL OR symbol = :symbol
            """
        ),
        {"symbol": symbol},
    ).mappings().one())
    wins, losses = stats["wins"], stats["losses"]
    return {**stats, "win_rate_pct": wins / (wins + losses) * 100 if wins + losses else None,
            "profit_factor": stats["gross_win_usd"] / stats["gross_loss_usd"] if stats["gross_loss_usd"] else None}


def _coin_view(connection, strategy: dict, usdt_free: Decimal, open_rows: list[dict],
               interval: str, now: datetime, fee_context: FeeContext, with_chart: bool = True) -> dict:
    """Everything one coin page needs: market, entry setup, lots, activity and chart."""
    bucket_sql, bucket_minutes = CHART_INTERVALS[interval]
    breakout_rule = ConsolidationConfig.from_strategy(strategy)
    pullback_rule = PullbackConfig.from_strategy(strategy)
    pyramid_rule = PyramidConfig.from_strategy(strategy)
    config = ExecutionConfig.from_strategy(strategy)
    symbol = strategy["market"]["symbol"]
    strategy_id = strategy["strategy_id"]
    zone = Decimal(str(strategy["entry"]["touch_zone_pct"])) / 100
    market = connection.execute(
        text("SELECT open_time, open, high, low, close FROM candles_1m WHERE symbol=:s ORDER BY open_time DESC LIMIT 1"),
        {"s": symbol},
    ).mappings().one_or_none()
    day_ago = connection.execute(
        text("SELECT close FROM candles_1m WHERE symbol=:s AND open_time <= :t ORDER BY open_time DESC LIMIT 1"),
        {"s": symbol, "t": (market["open_time"] if market else now) - timedelta(hours=24)},
    ).scalar_one_or_none()
    averages = connection.execute(
        text(
            """
            SELECT effective_at, signal_average, average_7d, average_15d, average_30d FROM daily_averages
            WHERE symbol=:s AND effective_at <= :now ORDER BY effective_at DESC LIMIT 1
            """
        ),
        {"s": symbol, "now": now},
    ).mappings().one_or_none()
    signal_state = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:k"), {"k": f"signal_engine:{symbol}"}
    ).scalar_one_or_none() or {}
    signals = [dict(row) for row in connection.execute(
        text(
            """
            SELECT e.episode_id, e.touch_time, e.average_value, e.status AS episode_status, e.details,
                   s.signal_id, s.status, s.reason, s.entry_time
            FROM touch_episodes e LEFT JOIN signals s ON s.episode_id=e.episode_id
            WHERE e.strategy_id=:id ORDER BY e.touch_time DESC LIMIT 25
            """
        ),
        {"id": strategy_id},
    ).mappings().all()]
    signal_counts = dict(connection.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE dip) AS touches,
                   count(*) FILTER (WHERE dip AND status='confirmed') AS confirmed,
                   count(*) FILTER (WHERE dip AND status='skipped_time_window') AS skipped_time_window,
                   count(*) FILTER (WHERE dip AND status='rejected_market_regime') AS rejected_trend,
                   count(*) FILTER (WHERE dip AND status IN ('cancelled_at_episode_exit','expired_wait_limit')) AS not_confirmed,
                   count(*) FILTER (WHERE dip AND status='observed_not_from_below') AS not_from_below,
                   count(*) FILTER (WHERE kind='consolidation') AS breakouts,
                   count(*) FILTER (WHERE kind='consolidation' AND status='confirmed') AS breakouts_confirmed,
                   count(*) FILTER (WHERE kind='pullback') AS pullbacks,
                   count(*) FILTER (WHERE kind='pullback' AND status='confirmed') AS pullbacks_confirmed,
                   count(*) FILTER (WHERE kind='pullback' AND status='skipped_time_window') AS pullbacks_skipped
            FROM (SELECT status, details->>'kind' AS kind, details->>'kind' IS NULL AS dip
                  FROM touch_episodes WHERE strategy_id=:id) episodes
            """
        ),
        {"id": strategy_id},
    ).mappings().one())
    trades = [dict(row) for row in connection.execute(
        text("SELECT * FROM trades WHERE symbol=:s ORDER BY exit_time DESC LIMIT 25"), {"s": symbol}
    ).mappings().all()]
    orders = [dict(row) for row in connection.execute(
        text(
            """
            SELECT o.*, p.symbol FROM orders o JOIN positions p USING (position_id)
            WHERE p.symbol=:s ORDER BY o.requested_at DESC, o.side LIMIT 30
            """
        ),
        {"s": symbol},
    ).mappings().all()]
    # The chart reads up to 160 buckets of candles - most of the table for a 1d chart - so it is only built for
    # the coin page actually on screen, not for all five coins on every refresh.
    chart: list[dict] = []
    if with_chart:
        chart = [dict(row) for row in connection.execute(
            text(
                f"""
                WITH source AS (
                    SELECT * FROM candles_1m WHERE symbol=:s
                      AND open_time >= (SELECT max(open_time) FROM candles_1m WHERE symbol=:s) - make_interval(mins => :lookback)
                ), buckets AS (
                    SELECT date_bin(INTERVAL '{bucket_sql}', open_time, TIMESTAMPTZ '1970-01-01') AS open_time,
                           (array_agg(open ORDER BY open_time))[1] AS open, max(high) AS high, min(low) AS low,
                           (array_agg(close ORDER BY open_time DESC))[1] AS close
                    FROM source GROUP BY 1
                )
                SELECT b.*, a.signal_average FROM buckets b
                LEFT JOIN daily_averages a ON a.symbol=:s AND a.effective_at=date_trunc('day', b.open_time)
                ORDER BY b.open_time
                """
            ),
            {"s": symbol, "lookback": bucket_minutes * 160},
        ).mappings().all()]
        if config.trend_exit_ema_minutes:
            _trend_line(connection, symbol, chart, config.trend_exit_ema_minutes, bucket_minutes)
        if breakout_rule:
            _consolidation_band(connection, symbol, chart, breakout_rule, bucket_minutes)
        if pullback_rule:
            _pullback_overlay(connection, symbol, chart, pullback_rule, bucket_minutes)
    markers: list[dict] = []
    if with_chart:
        markers = [dict(row) for row in connection.execute(
            text(
                """
                SELECT * FROM (
                    SELECT position_id, lot_number, entry_source, parent_position_id, entry_time,
                           entry_fill_price, exit_time,
                           exit_fill_price, exit_reason, realized_pnl_usd, status, trailing_started_at,
                           trend_exit_active,
                           entry_fill_price * (1 + :activation / 100.0) AS trailing_start_price,
                           row_number() OVER (ORDER BY entry_time, position_id) AS trade_number
                    FROM positions WHERE symbol=:s
                ) numbered
                WHERE entry_time >= :start OR exit_time >= :start OR status='open' ORDER BY entry_time
                """
            ),
            {"s": symbol, "start": chart[0]["open_time"] if chart else now, "activation": config.trail_activation_pct},
        ).mappings().all()]
    stats = _trade_stats(connection, symbol)
    # The coin's row only holds its switch and extra-entry toggles now; money and lots belong to the shared pot.
    allocation = read_allocation(connection, symbol) or CoinAllocation.default(strategy)
    pot = read_pot(connection)
    trading_enabled = read_trading_enabled(connection, symbol)
    configured = trading_enabled

    mark = market["close"] if market else None
    average = averages["signal_average"] if averages else None
    lower = average * (1 - zone) if average else None
    upper = average * (1 + zone) if average else None
    regime = "missing"
    if averages and None not in (averages["average_7d"], averages["average_15d"], averages["average_30d"]):
        a7, a15, a30 = averages["average_7d"], averages["average_15d"], averages["average_30d"]
        regime = "bullish" if a7 > a15 > a30 else "bearish" if a7 < a15 < a30 else "neutral"
    blocked = strategy["entry"].get("blocked_entry_hours_utc")
    in_block = bool(blocked and blocked["start"] <= now.hour < blocked["end"])
    if blocked:
        change_hour = blocked["end"] if in_block else blocked["start"]
        window_change = now.replace(hour=change_hour % 24, minute=0, second=0, microsecond=0)
        if window_change <= now:
            window_change += timedelta(days=1)
    else:
        window_change = None
    zone_state = None
    if mark is not None and lower is not None:
        zone_state = "below" if mark < lower else "above" if mark > upper else "inside"
    positions = [row for row in open_rows if row["symbol"] == symbol]
    open_lots = len(positions)
    open_by_source: dict[str, int] = {}
    for row in positions:
        open_by_source[row["entry_source"]] = open_by_source.get(row["entry_source"], 0) + 1
    open_cost = sum((row["allocation_usd"] for row in positions), ZERO)
    # Every coin draws on the pot's lots, so free slots are counted across all coins.
    free_slots = max(0, pot.lots - len(open_rows))
    next_lot_usd = (affordable_lot(pot.lot_size_usd, usdt_free)
                    if trading_enabled and free_slots and pot.lot_size_usd > ZERO else None)

    # Every way in is simply on or off, and they all share the coin's lots, first come first served.
    supported = {"dip": True, "breakout": breakout_rule is not None,
                 "pullback": pullback_rule is not None, "pyramid": pyramid_rule is not None}
    entries = {name: {"supported": supported[name],
                      "enabled": supported[name] and allocation.enabled(name),
                      "open_lots": open_by_source.get("signal" if name == "dip" else name, 0)}
               for name in MODULES}

    # One row per lot the coin owns, in the order they were bought, so the page can draw the pool rather than
    # describe it. Free slots are listed too - an empty slot is what the next signal will fill.
    marks = {symbol: mark}
    for other in {row["symbol"] for row in open_rows} - {symbol}:
        marks[other] = connection.execute(
            text("SELECT close FROM candles_1m WHERE symbol=:s ORDER BY open_time DESC LIMIT 1"), {"s": other}
        ).scalar_one_or_none()

    def slot_of(index: int, row: dict | None) -> dict:
        if row is None:
            return {"number": index, "state": "free", "source": None, "symbol": None, "mine": False}
        armed = bool(row["trailing_active"])
        rides = bool(row["trend_exit_active"]) and config.trend_exit_ema_minutes is not None
        # A slot can belong to another coin in the shared pot, so it is valued at that coin's own price.
        row_mark = marks.get(row["symbol"])
        value = row["quantity"] * row_mark if row_mark else None
        return {"number": index, "state": "open", "source": row["entry_source"], "symbol": row["symbol"],
                "label": coin_label(row["symbol"]), "mine": row["symbol"] == symbol,
                "position_id": row["position_id"], "entry_time": row["entry_time"],
                "entry_fill_price": row["entry_fill_price"], "allocation_usd": row["allocation_usd"],
                "mode": "trend" if rides else "giveback", "armed": armed,
                "trend_exit_pending": bool(row["trend_exit_pending"]),
                "stop_price": row["stop_price"], "parent_position_id": row["parent_position_id"],
                "unrealized_usd": None if value is None else value - row["allocation_usd"],
                "unrealized_pct": None if value is None else (value / row["allocation_usd"] - 1) * 100}

    # The pot's slots as a whole, every coin's lots in the order they were bought; this coin's are marked.
    ordered = sorted(open_rows, key=lambda row: row["entry_time"])
    slots = [slot_of(index + 1, ordered[index] if index < len(ordered) else None)
             for index in range(max(pot.lots, len(ordered)))]
    lot = {"next_lot_usd": next_lot_usd, "lot_number": len(open_rows) + 1,
           "slot_free": free_slots > 0, "free_lots": free_slots, "slots": slots,
           "free_usdt": usdt_free, "shared_open_lots": len(open_rows),
           "shortfall_usd": max(ZERO, pot.lot_size_usd - usdt_free)}
    open_value = sum((row["quantity"] * mark for row in positions), ZERO) if mark else ZERO
    market_age = (now - market["open_time"]).total_seconds() - 60 if market else None
    label = coin_label(symbol)
    return {
        "symbol": symbol, "label": label, "name": COIN_NAMES.get(symbol, label),
        "trading_enabled": trading_enabled, "configured": configured,
        "pending_trading_change": None,
        "strategy": {
            "strategy_id": strategy_id, "name": strategy["name"], "symbol": symbol,
            "signal_timeframe": strategy["market"]["signal_timeframe"],
            "signal_average_days": strategy["averages"]["signal_average_days"],
            "touch_zone_pct": strategy["entry"]["touch_zone_pct"],
            "confirmation_wait_minutes": strategy["entry"]["confirmation"]["maximum_wait_minutes"],
            "blocked_entry_hours_utc": blocked, "stop_pct": config.stop_pct,
            "requires_close_above_30d": (strategy["entry"].get("trend_filter") or {}).get("type")
            == "confirmation_close_above_average_30d",
            "maximum_above_30d_pct": (strategy["entry"].get("trend_filter") or {}).get("maximum_above_average_pct"),
            "trail_activation_pct": config.trail_activation_pct, "trail_giveback_pct": config.trail_giveback_pct,
            "usdt_fee_bps": config.usdt_fee_bps, "bnb_fee_bps": config.bnb_fee_bps, "slippage_bps": config.slippage_bps,
            "backtest": strategy["provenance"]["backtest_bnb_fees"],
            "pullback": None if pullback_rule is None else {
                "ema_minutes": pullback_rule.ema_minutes, "dwell_minutes": pullback_rule.dwell_minutes,
                "requires_uptrend": pullback_rule.requires_uptrend},
            "pyramid": None if pyramid_rule is None else {
                "step_pct": pyramid_rule.step_pct, "maximum_adds": pyramid_rule.maximum_adds,
                "add_exit": pyramid_rule.add_exit},
            "drawdown_review_pct": strategy["evaluation"]["maximum_drawdown_review_pct"],
        },
        "health": {
            "market_age_seconds": round(market_age, 1) if market_age is not None else None,
            "signal_engine": signal_state.get("status", "starting"),
        },
        "market": {
            "price": mark, "open_time": market["open_time"] if market else None,
            "change_24h_pct": (mark / day_ago - 1) * 100 if mark and day_ago else None,
        },
        "setup": {
            "signal_average": average, "zone_lower": lower, "zone_upper": upper, "zone_state": zone_state,
            "distance_to_zone_pct": ((lower / mark - 1) * 100 if zone_state == "below" else
                                     (mark / upper - 1) * 100 if zone_state == "above" else ZERO)
            if zone_state else None,
            "average_7d": averages["average_7d"] if averages else None,
            "average_15d": averages["average_15d"] if averages else None,
            "average_30d": averages["average_30d"] if averages else None,
            "regime": regime, "trend_allows_entries": regime in ("bullish", "neutral"),
            "entry_window_open": not in_block, "entry_window_changes_at": window_change,
            "pending_episode_since": signal_state.get("pending_since"),
            "signal_engine": signal_state.get("status", "starting"),
            "activation_at": signal_state.get("activation_at"),
        },
        "consolidation": _consolidation_view(connection, symbol, strategy["strategy_id"],
                                             breakout_rule, mark),
        "pullback": _pullback_view(connection, symbol, strategy_id, pullback_rule, mark, regime),
        "pyramid": _pyramid_view(connection, symbol, pyramid_rule, allocation, positions, mark,
                                 chart[-1].get("trend_line") if chart else None),
        "entries": entries,
        # What a lot bought right now would do when it wins: ride the trend line, or give profit back.
        "exit_plan": {
            "has_trend_exit": config.trend_exit_ema_minutes is not None,
            "ema_minutes": config.trend_exit_ema_minutes,
            "requires_uptrend": config.trend_exit_requires_uptrend,
            "next_lot_mode": ("trend" if config.trend_exit_ema_minutes is not None
                              and (regime == "bullish" or not config.trend_exit_requires_uptrend)
                              else "giveback"),
            "trend_line": chart[-1].get("trend_line") if chart else None,
            "giveback_pct": config.trail_giveback_pct,
            "activation_pct": config.trail_activation_pct,
            "stop_pct": config.stop_pct,
        },
        "lots": {**lot, "open_lots": open_lots, "max_lots": pot.lots,
                 "lot_size_usd": pot.lot_size_usd, "target_capital_usd": pot.total_usd},
        "money": {
            "symbol": symbol, "name": COIN_NAMES.get(symbol, label), "label": label,
            "trading_enabled": trading_enabled, "configured": configured,
            "lot_size_usd": pot.lot_size_usd, "lots": pot.lots,
            "entries": {name: {"enabled": allocation.enabled(name) and supported[name],
                               "supported": supported[name]} for name in MODULES},
            "target_capital_usd": pot.total_usd,
            "open_lots": open_lots, "open_cost_usd": open_cost, "open_value_usd": open_value,
            "capital_usd": open_cost, "value_usd": open_value,
            "realized_pnl_usd": stats["realized_usd"], "unrealized_pnl_usd": open_value - open_cost,
        },
        "stats": stats,
        "signal_counts": signal_counts,
        "positions": [_position_view(row, config, mark, fee_context, now) for row in positions],
        "signals": signals, "trades": trades, "orders": orders,
        "chart": chart, "markers": markers,
    }


@router.get("/dashboard")
def dashboard(interval: str = Query(default="15m"), chart: str | None = Query(default=None)) -> dict:
    """One consistent read model for every dashboard page: the account plus one section per coin.

    `chart` names the coin whose price chart is on screen; the other coins are sent without one.
    """
    if interval not in CHART_INTERVALS:
        raise HTTPException(status_code=422, detail=f"Unsupported chart interval: {interval}")
    chart_symbol = chart.upper() if chart else None
    strategies = load_strategies()
    first = next(iter(strategies.values()))
    fee_symbol = first["market"]["fee_symbol"]
    now = datetime.now(timezone.utc)
    binance = wallet()
    usdt_free = Decimal(str(binance.get("usdt", {}).get("free", "0"))) if binance.get("connected") else ZERO
    bnb_free = Decimal(str(binance.get("bnb", {}).get("free", "0"))) if binance.get("connected") else ZERO
    with get_engine().begin() as connection:
        account = _latest_snapshot(connection)
        settings = read_settings(connection)
        shadow = shadow_account(connection, settings) if settings.get("trading_mode") != "live" else None
        if shadow:
            usdt_free = shadow["free"]  # shadow buys spend the pretend wallet
        open_rows = [dict(row) for row in connection.execute(
            text("SELECT * FROM positions WHERE status='open' ORDER BY entry_time")
        ).mappings().all()]
        bnb_market = connection.execute(
            text("SELECT open_time, close FROM candles_1m WHERE symbol=:s ORDER BY open_time DESC LIMIT 1"),
            {"s": fee_symbol},
        ).mappings().one_or_none()
        fee_context = FeeContext(bool(binance.get("bnb_fee_discount")), bnb_free,
                                 bnb_market["close"] if bnb_market else None)
        coins = {symbol: _coin_view(connection, strategy, usdt_free, open_rows, interval, now, fee_context,
                                    with_chart=symbol == chart_symbol)
                 for symbol, strategy in strategies.items()}
        execution_state = connection.execute(
            text("SELECT value FROM engine_state WHERE key='live_execution'")
        ).scalar_one_or_none() or {}
        monitor = connection.execute(
            text("SELECT value FROM engine_state WHERE key='monitoring'")
        ).scalar_one_or_none() or {}
        trades = [dict(row) for row in connection.execute(
            text("SELECT * FROM trades ORDER BY exit_time DESC LIMIT 25")
        ).mappings().all()]
        requests = [dict(row) for row in connection.execute(
            text("SELECT * FROM control_requests ORDER BY requested_at DESC LIMIT 25")
        ).mappings().all()]
        stats = _trade_stats(connection, None)
        budget = _budget(connection, usdt_free)
        if shadow:
            # Shadow mode: the money is the shadow wallet (free + what its open lots cost).
            budget["budget_usd"] = shadow["free"] + shadow["open_cost"]
            budget["left_usd"] = budget["budget_usd"] - budget["allocated_usd"]
        pot = read_pot(connection)
        bnb_usage = dict(connection.execute(
            text(
                """
                SELECT COALESCE(sum(fee_bnb), 0) AS bnb_spent, COALESCE(sum(fee_usd) FILTER (WHERE fee_asset='BNB'), 0) AS bnb_fees_usd,
                       COALESCE(sum(fee_usd) FILTER (WHERE fee_asset='USDT'), 0) AS usdt_fees_usd,
                       count(*) FILTER (WHERE fee_asset='BNB') AS bnb_fills, count(*) FILTER (WHERE fee_asset='USDT') AS usdt_fills
                FROM orders
                """
            )
        ).mappings().one())
        alerts = [dict(row) for row in connection.execute(
            text(
                """
                SELECT alert_key, severity, status, title, message, first_seen_at, last_seen_at, resolved_at
                FROM monitoring_alerts ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, last_seen_at DESC LIMIT 15
                """
            )
        ).mappings().all()]
        logs = [dict(row) for row in connection.execute(
            text("SELECT id, timestamp, level, component, event_type, details FROM system_events ORDER BY timestamp DESC LIMIT 30")
        ).mappings().all()]
    config = ExecutionConfig.from_strategy(first)
    # BNB coverage is measured on the largest lot any coin buys.
    lot_size = pot.lot_size_usd
    round_trip_usd = bnb_round_trip_usd(first, lot_size)
    bnb_price = bnb_market["close"] if bnb_market else None
    bnb_balance = bnb_free
    bnb_value = bnb_balance * bnb_price if bnb_price else ZERO
    ages = [coin["health"]["market_age_seconds"] for coin in coins.values()]
    positions = [position for coin in coins.values() for position in coin["positions"]]
    positions.sort(key=lambda position: position["entry_time"])
    return {
        "generated_at": now,
        "coin_order": list(coins),
        "coins": coins,
        "health": {
            "status": monitor.get("status", "starting"),
            "market_age_seconds": None if None in ages else max(ages),
            "coins_updated": {symbol: (execution_state.get(symbol) or {}).get("last_open_time")
                              for symbol in coins},
        },
        "account": account,
        "binance": {"connected": bool(binance.get("connected")), "message": binance.get("message"),
                    "usdt_free": usdt_free, "wallet_value_usdt": binance.get("total_value_usdt"),
                    "checks": binance.get("checks", [])},
        "trading": {"mode": settings.get("trading_mode", "shadow"),
                    "daily_loss_limit_usd": settings.get("daily_loss_limit_usd"),
                    "maximum_open_value_usd": settings.get("maximum_open_value_usd"),
                    "shadow_start_usd": settings.get("shadow_start_usd")},
        "shadow": ({key: str(value) for key, value in shadow.items()} if shadow else None),
        "money": {
            "usdt_free": usdt_free,
            "budget_usd": budget["budget_usd"],
            "left_to_allocate_usd": budget["left_usd"],
            "allocated_usd": budget["allocated_usd"],
            "pot": {"lots": pot.lots, "lot_size_usd": pot.lot_size_usd, "total_usd": pot.total_usd,
                    "open_lots": len(open_rows), "free_lots": max(0, pot.lots - len(open_rows)),
                    "next_lot_usd": (affordable_lot(pot.lot_size_usd, usdt_free)
                                     if len(open_rows) < pot.lots and pot.lot_size_usd > ZERO else None),
                    "coins_on": sum(1 for coin in coins.values() if coin["trading_enabled"])},
            "in_trades_usd": sum((Decimal(str(coin["money"]["open_cost_usd"])) for coin in coins.values()), ZERO),
            "suggested_pot": (lambda plan: {"lots": plan.lots, "lot_size_usd": plan.lot_size_usd} if plan else None)(
                suggested_pot(budget["budget_usd"], Decimal(str(first["portfolio"]["minimum_lot_size_usd"])))),
            "pot_set_by_user": bool(settings.get("pot_set_by_user")),
            "limits": {"minimum_lot_usd": first["portfolio"]["minimum_lot_size_usd"],
                       "maximum_lot_usd": first["portfolio"]["maximum_lot_size_usd"],
                       "maximum_lots": first["portfolio"]["maximum_lots_per_coin"]},
            "coins": [coin["money"] for coin in coins.values()],
        },
        "bnb": {
            "enabled": bool(binance.get("bnb_fee_discount")), "price": bnb_price, "balance": bnb_balance,
            "value_usd": bnb_value, "lot_size_usd": lot_size, "round_trip_fee_usd": round_trip_usd,
            "round_trip_fee_bnb": round_trip_usd / bnb_price if bnb_price else None,
            "round_trips_left": int(bnb_value / round_trip_usd) if round_trip_usd else None,
            "spent_bnb": bnb_usage["bnb_spent"], "bnb_fees_usd": bnb_usage["bnb_fees_usd"],
            "usdt_fees_usd": bnb_usage["usdt_fees_usd"], "bnb_fills": bnb_usage["bnb_fills"],
            "usdt_fills": bnb_usage["usdt_fills"],
            "saved_usd": bnb_usage["bnb_fees_usd"] * (config.usdt_fee_bps / config.bnb_fee_bps - 1),
            "updated_at": bnb_market["open_time"] if bnb_market else None,
        },
        "stats": stats,
        "positions": positions, "trades": trades, "requests": requests,
        "chart_interval": interval, "alerts": alerts, "logs": logs,
    }


@router.get("/equity-history")
def equity_history(period: str = Query(default="7d")) -> dict:
    """Wallet value and trading profit over time, from the per-minute snapshots."""
    now = datetime.now(timezone.utc)
    with get_engine().connect() as connection:
        first = connection.execute(text("SELECT min(timestamp) FROM account_snapshots")).scalar_one()
        if period == "all":
            start = first or now - timedelta(days=1)
        elif period in EQUITY_PERIOD_DAYS:
            start = now - timedelta(days=EQUITY_PERIOD_DAYS[period])
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported period: {period}")
        bucket = _equity_bucket(now - max(start, first or start))
        rows = connection.execute(
            text(
                f"""
                SELECT date_bin(INTERVAL '{bucket}', timestamp, TIMESTAMPTZ '1970-01-01') AS timestamp,
                       (array_agg(wallet_value_usd ORDER BY timestamp DESC))[1] AS wallet_value_usd,
                       (array_agg(usdt_free ORDER BY timestamp DESC))[1] AS usdt_free,
                       (array_agg(open_position_value_usd ORDER BY timestamp DESC))[1] AS positions_usd,
                       (array_agg(bnb_value_usd ORDER BY timestamp DESC))[1] AS bnb_value_usd,
                       (array_agg(strategy_pnl_usd ORDER BY timestamp DESC))[1] AS strategy_pnl_usd,
                       (array_agg(realized_pnl_usd ORDER BY timestamp DESC))[1] AS realized_pnl_usd
                FROM account_snapshots WHERE timestamp BETWEEN :start AND :end GROUP BY 1 ORDER BY 1
                """
            ),
            {"start": start, "end": now},
        ).mappings().all()
    points = [dict(row) for row in rows]
    summary = None
    if points:
        pnl = [point["strategy_pnl_usd"] for point in points]
        summary = {"strategy_pnl_change_usd": pnl[-1] - pnl[0],
                   "high_value_usd": max(p["wallet_value_usd"] for p in points),
                   "low_value_usd": min(p["wallet_value_usd"] for p in points)}
    # The chart spans the whole range asked for, so a week with one day of history shows as the last day of a week.
    return {"period": period, "bucket": bucket, "start": start, "end": now, "points": points, "summary": summary}


@router.get("/leaderboard")
def leaderboard(period: str = Query(default="7d")) -> dict:
    """Coins ranked by what they actually made: closed trades plus open lots at today's price."""
    if period != "all" and period not in LEADERBOARD_PERIOD_DAYS:
        raise HTTPException(status_code=422, detail=f"Unsupported period: {period}")
    strategies = load_strategies()
    prices = _prices(list(strategies))
    now = datetime.now(timezone.utc)
    start = (datetime(2020, 1, 1, tzinfo=timezone.utc) if period == "all"
             else now - timedelta(days=LEADERBOARD_PERIOD_DAYS[period]))
    with get_engine().connect() as connection:
        trades = [dict(row) for row in connection.execute(
            text("""SELECT symbol, exit_time, net_pnl_usd FROM trades
                    WHERE exit_time >= :start ORDER BY exit_time"""),
            {"start": start},
        ).mappings().all()]
        open_rows = [dict(row) for row in connection.execute(
            text("SELECT symbol, quantity, allocation_usd FROM positions WHERE status='open'")
        ).mappings().all()]
        enabled_by_coin = {symbol: read_trading_enabled(connection, symbol) for symbol in strategies}
        pot = read_pot(connection)
    coins = []
    for symbol in strategies:
        enabled = enabled_by_coin[symbol]
        coin_trades = [row for row in trades if row["symbol"] == symbol]
        coin_open = [row for row in open_rows if row["symbol"] == symbol]
        realized = sum((row["net_pnl_usd"] for row in coin_trades), ZERO)
        unrealized = sum((row["quantity"] * prices.get(symbol, ZERO) - row["allocation_usd"] for row in coin_open), ZERO)
        # Coins share one pot, so each coin's return is measured against the whole pot it trades from.
        capital = pot.total_usd
        running = ZERO
        series = []
        for row in coin_trades:
            running += row["net_pnl_usd"]
            series.append({"t": row["exit_time"], "pnl_usd": running})
        coins.append({
            "symbol": symbol, "label": coin_label(symbol), "name": COIN_NAMES.get(symbol, coin_label(symbol)),
            "trading_enabled": enabled, "capital_usd": capital, "pnl_usd": realized + unrealized,
            "realized_usd": realized, "unrealized_usd": unrealized,
            "return_pct": (realized + unrealized) / capital * 100 if capital else ZERO,
            "trades": len(coin_trades), "wins": len([r for r in coin_trades if r["net_pnl_usd"] > 0]),
            "open_lots": len(coin_open), "series": series,
        })
    coins.sort(key=lambda coin: (coin["return_pct"], coin["pnl_usd"]), reverse=True)
    for rank, coin in enumerate(coins, start=1):
        coin["rank"] = rank
    return {"period": period, "start": start, "generated_at": now, "coins": coins}


PROFIT_PERIODS = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "90d": 90}


def _profit_window(period: str, start: datetime | None, end: datetime | None) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    if period == "custom":
        if not start or not end:
            raise HTTPException(status_code=422, detail="A custom range needs a start and an end date")
        return start, end, "custom"
    if period == "mtd":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now, period
    if period == "all":
        return datetime(2020, 1, 1, tzinfo=timezone.utc), now, period
    if period not in PROFIT_PERIODS:
        raise HTTPException(status_code=422, detail=f"Unsupported period: {period}")
    return now - timedelta(days=PROFIT_PERIODS[period]), now, period


def _profit_rows(connection, start: datetime, end: datetime) -> list[dict]:
    return [dict(row) for row in connection.execute(
        text("SELECT * FROM trades WHERE exit_time >= :start AND exit_time <= :end ORDER BY exit_time"),
        {"start": start, "end": end},
    ).mappings().all()]


def _summarize(rows: list[dict]) -> dict:
    """Costs are already inside net_pnl_usd; gross adds them back so both views are available."""
    fees = sum((row["entry_fee_usd"] + row["exit_fee_usd"] for row in rows), ZERO)
    bnb_fees = sum((row["bnb_fees_usd"] for row in rows), ZERO)
    net = sum((row["net_pnl_usd"] for row in rows), ZERO)
    wins = [row for row in rows if row["net_pnl_usd"] > 0]
    losses = [row for row in rows if row["net_pnl_usd"] < 0]
    won = sum((row["net_pnl_usd"] for row in wins), ZERO)
    lost = -sum((row["net_pnl_usd"] for row in losses), ZERO)
    traded = sum((row["allocation_usd"] for row in rows), ZERO)
    return {
        "trades": len(rows), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": len(wins) / len(rows) * 100 if rows else None,
        "gross_pnl_usd": net + fees, "fees_usd": fees, "fees_in_bnb_usd": bnb_fees,
        "fees_in_usdt_usd": fees - bnb_fees, "net_pnl_usd": net,
        "won_usd": won, "lost_usd": lost, "profit_factor": won / lost if lost else None,
        "average_win_usd": won / len(wins) if wins else None,
        "average_loss_usd": -lost / len(losses) if losses else None,
        "best_usd": max((row["net_pnl_usd"] for row in rows), default=None),
        "worst_usd": min((row["net_pnl_usd"] for row in rows), default=None),
        "traded_value_usd": traded,
        "return_on_traded_pct": net / traded * 100 if traded else None,
        "average_hold_minutes": sum((row["duration_minutes"] for row in rows), 0) / len(rows) if rows else None,
    }


@router.get("/profit")
def profit(period: str = Query(default="7d"), start: datetime | None = None, end: datetime | None = None) -> dict:
    """Money made in a period, after every cost, with a per-coin and per-day breakdown."""
    window_start, window_end, name = _profit_window(period, start, end)
    strategies = load_strategies()
    prices = _prices(list(strategies) + ["BNBUSDT"])
    with get_engine().connect() as connection:
        rows = _profit_rows(connection, window_start, window_end)
        open_rows = [dict(row) for row in connection.execute(
            text("SELECT symbol, quantity, allocation_usd, entry_time FROM positions WHERE status='open'")
        ).mappings().all()]
        bnb_spent = connection.execute(
            text("""SELECT COALESCE(sum(fee_asset_quantity),0) FROM orders
                    WHERE fee_asset='BNB' AND requested_at >= :start AND requested_at <= :end"""),
            {"start": window_start, "end": window_end},
        ).scalar_one()
    open_value = sum((row["quantity"] * prices.get(row["symbol"], ZERO) for row in open_rows), ZERO)
    open_cost = sum((row["allocation_usd"] for row in open_rows), ZERO)
    by_coin = []
    for symbol in strategies:
        coin_rows = [row for row in rows if row["symbol"] == symbol]
        coin_open = [row for row in open_rows if row["symbol"] == symbol]
        unrealized = sum((row["quantity"] * prices.get(symbol, ZERO) - row["allocation_usd"] for row in coin_open), ZERO)
        by_coin.append({"symbol": symbol, "label": coin_label(symbol), "open_lots": len(coin_open),
                        "unrealized_pnl_usd": unrealized, **_summarize(coin_rows)})
    by_coin.sort(key=lambda coin: coin["net_pnl_usd"], reverse=True)
    days: dict[str, dict] = {}
    for row in rows:
        day = row["exit_time"].date().isoformat()
        bucket = days.setdefault(day, {"date": day, "net_pnl_usd": ZERO, "trades": 0})
        bucket["net_pnl_usd"] += row["net_pnl_usd"]
        bucket["trades"] += 1
    running = ZERO
    daily = []
    for day in sorted(days):
        running += days[day]["net_pnl_usd"]
        daily.append({**days[day], "cumulative_usd": running})
    return {
        "period": name, "start": window_start, "end": window_end,
        "summary": {**_summarize(rows), "bnb_spent": bnb_spent,
                    "unrealized_pnl_usd": open_value - open_cost, "open_lots": len(open_rows),
                    "open_value_usd": open_value},
        "coins": by_coin, "daily": daily,
    }


@router.get("/profit/trades.csv")
def profit_trades_csv(period: str = Query(default="30d"), start: datetime | None = None,
                      end: datetime | None = None) -> Response:
    """The same trades as a spreadsheet file."""
    window_start, window_end, _ = _profit_window(period, start, end)
    with get_engine().connect() as connection:
        rows = _profit_rows(connection, window_start, window_end)
    columns = ["exit_time", "symbol", "entry_time", "entry_source", "quantity", "allocation_usd",
               "entry_fill_price", "exit_fill_price", "entry_fee_usd", "exit_fee_usd", "bnb_fees_usd",
               "exit_reason", "duration_minutes", "net_return_pct", "net_pnl_usd"]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return Response(buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="trades-{window_start:%Y%m%d}-{window_end:%Y%m%d}.csv"'})


@router.get("/monitoring/alerts")
def monitoring_alerts(include_resolved: bool = False) -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM monitoring_alerts WHERE :r OR status='active' ORDER BY last_seen_at DESC"),
            {"r": include_resolved},
        ).mappings().all()
    return {"alerts": [dict(row) for row in rows]}


@router.get("/monitoring/logs")
def monitoring_logs(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT id, timestamp, level, component, event_type, details FROM system_events ORDER BY timestamp DESC LIMIT :l"),
            {"l": limit},
        ).mappings().all()
    return {"logs": [dict(row) for row in rows]}


@router.get("/trades")
def all_trades(limit: int = Query(default=200, ge=1, le=5000)) -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(text("SELECT * FROM trades ORDER BY exit_time DESC LIMIT :l"), {"l": limit}).mappings().all()
    return {"trades": [dict(row) for row in rows]}
