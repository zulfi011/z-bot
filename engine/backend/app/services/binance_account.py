"""Read-only view of the Binance spot account for the dashboard.

Balances, what the API key is allowed to do, whether fees are paid in BNB, and the fee rates that apply. Nothing
here places or cancels an order.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock

from app.services.binance_client import BinanceClient, BinanceError

ZERO = Decimal("0")
CACHE_SECONDS = 30
_lock = Lock()
_cached: tuple[float, dict] | None = None


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return ZERO


def safety_checks(restrictions: dict, burn: dict, symbols: list[str]) -> list[dict]:
    """The dashboard's key-safety checklist, worst first."""
    checks: list[dict] = []
    if restrictions.get("enableWithdrawals"):
        checks.append({"level": "danger", "title": "Withdrawals are enabled on this key",
                       "detail": "Turn withdrawals off in Binance → API Management. The bot never needs them."})
    if not restrictions.get("ipRestrict"):
        checks.append({"level": "warning", "title": "The key is not locked to this server's IP",
                       "detail": "In Binance choose 'Restrict access to trusted IPs only' and enter this server's address."})
    else:
        checks.append({"level": "ok", "title": "Key locked to trusted IPs", "detail": "Only this server can use it."})
    if restrictions.get("enableSpotAndMarginTrading"):
        checks.append({"level": "ok", "title": "Spot trading allowed", "detail": "The bot can place orders once live trading is switched on."})
    else:
        checks.append({"level": "info", "title": "Spot trading is off on this key",
                       "detail": "Reading works; enable 'Spot & Margin Trading' in Binance before going live."})
    for flag, label in (("enableFutures", "Futures"), ("enableMargin", "Margin loans"),
                        ("permitsUniversalTransfer", "Universal transfer"), ("enableInternalTransfer", "Internal transfer")):
        if restrictions.get(flag):
            checks.append({"level": "warning", "title": f"{label} is enabled on this key",
                           "detail": "The bot only needs spot trading; switch this off in Binance."})
    expiry = restrictions.get("tradingAuthorityExpirationTime")
    if expiry:
        when = datetime.fromtimestamp(int(expiry) / 1000, tz=timezone.utc)
        checks.append({"level": "warning", "title": "Binance will expire this key's trading permission",
                       "detail": f"Trading stops working after {when:%d %b %Y}. Renew it in Binance before then."})
    if burn.get("spotBNBBurn"):
        checks.append({"level": "ok", "title": "Fees are paid in BNB", "detail": "0.075% per side instead of 0.10%."})
    else:
        checks.append({"level": "warning", "title": "BNB fee discount is off",
                       "detail": "Switch on 'Use BNB to pay for fees' in Binance to pay 0.075% instead of 0.10%."})
    if not symbols:
        checks.append({"level": "info", "title": "No coins configured", "detail": "Add a coin strategy first."})
    return checks


# Key permissions, the BNB-fee switch and fee rates change only when you edit them on Binance, so they are asked for
# every few minutes; balances are still read on every refresh.
SETTINGS_SECONDS = 600
_settings: dict[tuple, tuple[float, dict]] = {}


def _settled(key: tuple, fetch, raise_errors: bool = False) -> dict:
    cached = _settings.get(key)
    if cached and time.monotonic() - cached[0] < SETTINGS_SECONDS:
        return cached[1]
    try:
        value = fetch() or {}
    except BinanceError:
        if raise_errors:
            raise
        return cached[1] if cached else {}
    _settings[key] = (time.monotonic(), value)
    return value


def build(client: BinanceClient, symbols: list[str], prices: dict[str, Decimal], names: dict[str, str]) -> dict:
    """Everything the Binance card shows. Raises BinanceError if Binance rejects the key."""
    account = client.account()
    balances = {row["asset"]: (_decimal(row["free"]), _decimal(row["locked"]))
                for row in account.get("balances", [])}
    restrictions = _settled(("restrictions",), client.api_restrictions)
    burn = _settled(("burn",), client.bnb_burn)
    fees = {}
    for symbol in symbols:
        try:
            rates = _settled(("commission", symbol), lambda: client.commission(symbol), raise_errors=True)
            standard = rates.get("standardCommission", {})
            discount = rates.get("discount", {})
            fees[symbol] = {
                "maker_pct": float(_decimal(standard.get("maker")) * 100),
                "taker_pct": float(_decimal(standard.get("taker")) * 100),
                # Binance's "discount" is the share you still pay (0.75 = pay 75%), so the saving is 1 - discount.
                "bnb_discount_pct": float((1 - _decimal(discount.get("discount"))) * 100)
                if discount.get("enabledForAccount") and discount.get("discount") else 0.0,
            }
        except BinanceError:
            continue

    def value(asset: str, amount: Decimal) -> Decimal:
        if asset in ("USDT", "USDC", "BUSD", "FDUSD"):
            return amount
        return amount * prices.get(f"{asset}USDT", ZERO)

    coins = []
    for symbol in symbols:
        asset = symbol.removesuffix("USDT")
        free, locked = balances.get(asset, (ZERO, ZERO))
        coins.append({"symbol": symbol, "asset": asset, "name": names.get(symbol, asset),
                      "free": str(free), "locked": str(locked), "price": str(prices.get(symbol, ZERO)),
                      "value_usdt": str(value(asset, free + locked)), "fees": fees.get(symbol)})
    usdt_free, usdt_locked = balances.get("USDT", (ZERO, ZERO))
    bnb_free, bnb_locked = balances.get("BNB", (ZERO, ZERO))
    other = [{"asset": asset, "free": str(free), "value_usdt": str(value(asset, free + locked))}
             for asset, (free, locked) in sorted(balances.items())
             if asset not in {"USDT", "BNB"} | {s.removesuffix("USDT") for s in symbols}
             and value(asset, free + locked) >= Decimal("1")]
    total = sum((value(asset, free + locked) for asset, (free, locked) in balances.items()), ZERO)
    return {
        "connected": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "account_type": account.get("accountType"),
        "can_trade": bool(account.get("canTrade")),
        "usdt": {"free": str(usdt_free), "locked": str(usdt_locked)},
        "bnb": {"free": str(bnb_free), "locked": str(bnb_locked), "price": str(prices.get("BNBUSDT", ZERO)),
                "value_usdt": str(value("BNB", bnb_free + bnb_locked))},
        "coins": coins,
        "other_assets": other,
        "total_value_usdt": str(total),
        "restrictions": {key: restrictions.get(key) for key in
                         ("ipRestrict", "enableReading", "enableSpotAndMarginTrading", "enableWithdrawals",
                          "enableMargin", "enableFutures", "permitsUniversalTransfer", "enableInternalTransfer",
                          "tradingAuthorityExpirationTime")},
        "bnb_fee_discount": bool(burn.get("spotBNBBurn")),
        "checks": safety_checks(restrictions, burn, symbols),
    }


def snapshot(client: BinanceClient, symbols: list[str], prices: dict[str, Decimal], names: dict[str, str],
             force: bool = False) -> dict:
    """Cached account view; failures are returned (never raised) so the dashboard can explain them."""
    global _cached
    with _lock:
        if not force and _cached and time.monotonic() - _cached[0] < CACHE_SECONDS:
            return _cached[1]
    if not client.configured:
        result = {"connected": False, "state": "not_configured",
                  "message": "No Binance API key on this server yet. Add BINANCE_API_KEY and BINANCE_API_SECRET to "
                             "/opt/z-bot/.env and restart the app.",
                  "checked_at": datetime.now(timezone.utc).isoformat()}
    else:
        try:
            result = build(client, symbols, prices, names)
        except BinanceError as error:
            result = {"connected": False, "state": "rejected", "message": error.explanation,
                      "binance_code": error.code, "checked_at": datetime.now(timezone.utc).isoformat()}
    with _lock:
        _cached = (time.monotonic(), result)
    return result
