"""Everything the dashboard can change: Buy now, the pot, coin and entry switches, mode, money, closing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.api.common import MAX_AMOUNT, _authorize, _coin_symbol, _insert_request, free_usdt, supports
from app.core import control_session, credentials
from app.core.strategy import load_strategies, load_strategy
from app.db.session import get_engine
from app.domain.execution import MODULES, CoinAllocation
from app.services.account import (
    SETTINGS_KEY,
    affordable_lot,
    coin_label,
    open_lot_total,
    read_allocation,
    read_pot,
    read_settings,
    read_trading_enabled,
    shadow_account,
    suggested_pot,
)

router = APIRouter()


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
