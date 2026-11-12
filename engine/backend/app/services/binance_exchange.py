"""Placing, protecting and closing real spot positions on Binance.

Every order is built here so Binance's own rules are respected: the price tick, the quantity step and the minimum
order value. In shadow mode the same order is prepared and recorded but never sent, which is how live trading is
rehearsed safely.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from app.services.binance_client import BinanceClient, BinanceError

ZERO = Decimal("0")


EXCHANGE_INFO_SECONDS = 6 * 3600


def plain(value: Decimal) -> str:
    """Binance wants a plain number: no exponent, no trailing zeros."""
    return format(value.normalize(), "f")


def order_id_for(kind: str, key: str) -> str:
    """A client order id that is the same every time for the same lot and action.

    If the app stops after Binance filled an order but before the ledger recorded it, the same minute is processed
    again on restart. With a stable id the bot asks Binance first and records the earlier order instead of sending a
    second one. Binance allows 36 characters of letters, digits, '-' and '_'.
    """
    return f"z{kind}-" + hashlib.sha256(key.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class SymbolRules:
    """What Binance allows for one trading pair."""
    symbol: str
    step_size: Decimal          # quantity must be a multiple of this
    tick_size: Decimal          # price must be a multiple of this
    minimum_quantity: Decimal
    minimum_notional: Decimal   # smallest order value in USDT
    stop_loss_limit: bool       # can we park a protective order on the exchange?

    def round_quantity(self, quantity: Decimal) -> Decimal:
        if self.step_size <= ZERO:
            return quantity
        return (quantity / self.step_size).to_integral_value(rounding=ROUND_DOWN) * self.step_size

    def round_price(self, price: Decimal, up: bool = False) -> Decimal:
        if self.tick_size <= ZERO:
            return price
        rounding = ROUND_UP if up else ROUND_DOWN
        return (price / self.tick_size).to_integral_value(rounding=rounding) * self.tick_size

    def rejects_buy(self, quote_amount: Decimal) -> str | None:
        if quote_amount < self.minimum_notional:
            return (f"Binance's smallest {self.symbol} order is ${self.minimum_notional:.2f}; "
                    f"this lot is ${quote_amount:.2f}.")
        return None

    def rejects_sell(self, quantity: Decimal, price: Decimal) -> str | None:
        rounded = self.round_quantity(quantity)
        if rounded <= ZERO or rounded < self.minimum_quantity:
            return f"The amount to sell ({quantity}) is below Binance's minimum for {self.symbol}."
        if price > ZERO and rounded * price < self.minimum_notional:
            return (f"Selling {rounded} {self.symbol} is worth less than Binance's ${self.minimum_notional:.2f} "
                    "minimum; it stays open until it is worth more.")
        return None


@dataclass
class OrderResult:
    """What happened (or would have happened) with one order."""
    sent: bool
    client_order_id: str
    request: dict
    response: dict = field(default_factory=dict)
    error: str | None = None
    recovered: bool = False     # Binance already had this order from before a restart; nothing new was sent

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def exchange_order_id(self) -> str | None:
        value = self.response.get("orderId")
        return str(value) if value is not None else None

    @property
    def filled_quantity(self) -> Decimal:
        return Decimal(str(self.response.get("executedQty", "0") or "0"))

    @property
    def filled_quote(self) -> Decimal:
        return Decimal(str(self.response.get("cummulativeQuoteQty", "0") or "0"))

    @property
    def average_price(self) -> Decimal:
        quantity = self.filled_quantity
        return self.filled_quote / quantity if quantity > ZERO else ZERO

    def commission(self) -> tuple[Decimal, str]:
        """Total fee Binance charged for this order, and the asset it took it in."""
        total, asset = ZERO, "USDT"
        for fill in self.response.get("fills", []) or []:
            total += Decimal(str(fill.get("commission", "0") or "0"))
            asset = fill.get("commissionAsset", asset)
        return total, asset


class BinanceExchange:
    def __init__(self, client: BinanceClient, live: bool = False) -> None:
        self.client = client
        self.live = live
        self._rules: dict[str, SymbolRules] = {}
        self._rules_loaded_at = 0.0

    # ------------------------------------------------------------------ rules
    def rules(self, symbol: str) -> SymbolRules:
        if symbol not in self._rules or time.monotonic() - self._rules_loaded_at > EXCHANGE_INFO_SECONDS:
            self._load_rules(symbol)
        return self._rules[symbol]

    def _load_rules(self, symbol: str) -> None:
        payload = self.client._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
        for entry in payload.get("symbols", []):
            filters = {item["filterType"]: item for item in entry.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
            self._rules[entry["symbol"]] = SymbolRules(
                symbol=entry["symbol"],
                step_size=Decimal(str(lot.get("stepSize", "0"))),
                tick_size=Decimal(str(price.get("tickSize", "0"))),
                minimum_quantity=Decimal(str(lot.get("minQty", "0"))),
                minimum_notional=Decimal(str(notional.get("minNotional", notional.get("notional", "5")))),
                stop_loss_limit="STOP_LOSS_LIMIT" in (entry.get("orderTypes") or []),
            )
        self._rules_loaded_at = time.monotonic()

    # ------------------------------------------------------------------ orders
    def _send(self, action: str, params: dict, method: str = "POST", path: str = "/api/v3/order") -> OrderResult:
        client_order_id = params.get("newClientOrderId") or f"bot-{uuid.uuid4().hex[:20]}"
        params = {**params, "newClientOrderId": client_order_id} if method == "POST" else params
        if not self.live:
            return OrderResult(sent=False, client_order_id=client_order_id, request={"action": action, **params},
                               response={"shadow": True})
        if method == "POST" and "newClientOrderId" in params and not client_order_id.startswith("bot-"):
            try:
                earlier = self.find_order(params["symbol"], client_order_id)
            except BinanceError as error:
                # Unknown is not the same as absent: sending now could buy the same lot twice.
                return OrderResult(sent=False, client_order_id=client_order_id, request={"action": action, **params},
                                   error="Could not check Binance for an earlier copy of this order, so it was not "
                                         f"sent (it is retried next minute): {error.explanation}",
                                   response={"code": error.code, "msg": error.binance_message})
            # A filled or still-open copy is this order; a cancelled or expired one may be sent again.
            if earlier and earlier.get("status") in ("FILLED", "PARTIALLY_FILLED", "NEW"):
                return OrderResult(sent=True, client_order_id=client_order_id, request={"action": action, **params},
                                   response=self._with_fills(params["symbol"], earlier), recovered=True)
        try:
            response = self.client.signed_request(method, path, params)
            return OrderResult(sent=True, client_order_id=client_order_id,
                               request={"action": action, **params}, response=response or {})
        except BinanceError as error:
            return OrderResult(sent=True, client_order_id=client_order_id, request={"action": action, **params},
                               error=error.explanation, response={"code": error.code, "msg": error.binance_message})

    def find_order(self, symbol: str, client_order_id: str) -> dict | None:
        """The order Binance has under this client id, or None if it has never seen it."""
        try:
            return self.client.signed_get("/api/v3/order", {"symbol": symbol, "origClientOrderId": client_order_id})
        except BinanceError as error:
            if error.code == -2013:  # "Order does not exist"
                return None
            raise

    def _with_fills(self, symbol: str, order: dict) -> dict:
        """An order read back from Binance has no fills; add them from myTrades so fees are still recorded."""
        if order.get("fills") or order.get("status") != "FILLED":
            return order
        try:
            trades = self.my_trades(symbol, str(order["orderId"]))
        except BinanceError:
            trades = []
        return {**order, "fills": [{"price": trade.get("price"), "qty": trade.get("qty"),
                                    "commission": trade.get("commission", "0"),
                                    "commissionAsset": trade.get("commissionAsset", "USDT")} for trade in trades]}

    def market_buy(self, symbol: str, quote_amount: Decimal, client_order_id: str | None = None) -> OrderResult:
        """Spend exactly `quote_amount` USDT at the market price."""
        amount = quote_amount.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        params = {"symbol": symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": plain(amount)}
        return self._send("market_buy", {**params, **({"newClientOrderId": client_order_id} if client_order_id else {})})

    def best_bid_ask(self, symbol: str) -> tuple[Decimal, Decimal]:
        """Decision-time top of book used only for execution-quality measurement."""
        payload = self.client._request("GET", "/api/v3/ticker/bookTicker", {"symbol": symbol})
        return Decimal(str(payload["bidPrice"])), Decimal(str(payload["askPrice"]))

    def market_sell(self, symbol: str, quantity: Decimal, client_order_id: str | None = None) -> OrderResult:
        rules = self.rules(symbol)
        amount = rules.round_quantity(quantity)
        params = {"symbol": symbol, "side": "SELL", "type": "MARKET", "quantity": plain(amount)}
        return self._send("market_sell", {**params, **({"newClientOrderId": client_order_id} if client_order_id else {})})

    def stop_trigger(self, symbol: str, stop_price: Decimal) -> Decimal:
        """The trigger price Binance will actually hold: the stop rounded down to the price tick."""
        return self.rules(symbol).round_price(stop_price) if self.live else stop_price

    def protective_stop(self, symbol: str, quantity: Decimal, stop_price: Decimal,
                        slip_pct: Decimal = Decimal("0.5"), client_order_id: str | None = None) -> OrderResult:
        """Park a stop-loss on Binance so a crash still sells even if this app is down.

        The limit price sits below the trigger so it fills in a fast drop; Binance rejects a limit that is too far,
        which is why the gap is small.
        """
        rules = self.rules(symbol)
        amount = rules.round_quantity(quantity)
        trigger = rules.round_price(stop_price)
        limit = rules.round_price(stop_price * (1 - slip_pct / 100))
        params = {"symbol": symbol, "side": "SELL", "type": "STOP_LOSS_LIMIT", "timeInForce": "GTC",
                  "quantity": plain(amount), "stopPrice": plain(trigger), "price": plain(limit)}
        return self._send("protective_stop",
                          {**params, **({"newClientOrderId": client_order_id} if client_order_id else {})})

    def cancel(self, symbol: str, order_id: str) -> OrderResult:
        return self._send("cancel", {"symbol": symbol, "orderId": order_id}, method="DELETE")

    def order_status(self, symbol: str, order_id: str) -> dict:
        return self.client.signed_get("/api/v3/order", {"symbol": symbol, "orderId": order_id})

    def open_orders(self, symbol: str | None = None) -> list[dict]:
        return self.client.signed_get("/api/v3/openOrders", {"symbol": symbol} if symbol else None) or []

    def my_trades(self, symbol: str, order_id: str) -> list[dict]:
        return self.client.signed_get("/api/v3/myTrades", {"symbol": symbol, "orderId": order_id}) or []
