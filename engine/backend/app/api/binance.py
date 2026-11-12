"""Attaching, checking and detaching the user's Binance account."""

from __future__ import annotations

import re

from fastapi import APIRouter, Cookie, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from app.api.common import _authorize, _binance_client, _prices
from app.core import control_session, credentials
from app.core.settings import get_settings
from app.core.strategy import COIN_NAMES, load_strategies
from app.db.session import get_engine
from app.services import binance_account, binance_reachability
from app.services.account import coin_label, read_settings
from app.services.binance_client import BinanceClient, BinanceError

router = APIRouter()


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
