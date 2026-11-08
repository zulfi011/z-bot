"""A pretend Binance spot account for trying the whole app with money in it, without any real money.

Prices are Binance's real public prices; the wallet, the orders and the fills are simulated. Market orders fill at
the current price, fees are taken in BNB, and parked STOP_LOSS_LIMIT orders fill once the real price falls through
their trigger. Start it with devtools/docker-compose.fake-binance.yml (see the README there). Never point a real
key at it, and never run it on the trading server.
"""

from __future__ import annotations

import json
import os
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

PORT = int(os.environ.get("PORT", "9000"))
START_USDT = Decimal(os.environ.get("FAKE_USDT", "300"))
START_BNB = Decimal(os.environ.get("FAKE_BNB", "0.02"))
PUBLIC = "https://data-api.binance.vision/api/v3/ticker/price?symbol="
FEE = Decimal("0.00075")  # 0.075%: the BNB-discounted taker fee
RULES = {  # stepSize, tickSize - close to Binance's real filters for these pairs
    "SOLUSDT": ("0.001", "0.01"), "ETHUSDT": ("0.0001", "0.01"), "BTCUSDT": ("0.00001", "0.01"),
    "AAVEUSDT": ("0.001", "0.01"), "TRXUSDT": ("0.1", "0.0001"), "BNBUSDT": ("0.001", "0.01"),
}

lock = threading.Lock()
balances: dict[str, Decimal] = {"USDT": START_USDT, "BNB": START_BNB}
locked: dict[str, Decimal] = {}
orders: dict[int, dict] = {}
next_id = [1000]
prices: dict[str, tuple[float, Decimal]] = {}


def price(symbol: str) -> Decimal:
    cached = prices.get(symbol)
    if cached and time.monotonic() - cached[0] < 5:
        return cached[1]
    with urlopen(PUBLIC + symbol, timeout=5) as response:
        value = Decimal(json.loads(response.read())["price"])
    prices[symbol] = (time.monotonic(), value)
    return value


def asset(symbol: str) -> str:
    return symbol.removesuffix("USDT")


def fill(order: dict, at: Decimal) -> None:
    """Settle an order at a price: move the coins, charge the fee in BNB."""
    quantity = Decimal(order["origQty"])
    quote = quantity * at
    coin = asset(order["symbol"])
    fee_bnb = (quote * FEE / price("BNBUSDT")).quantize(Decimal("0.00000001"))
    if order["side"] == "BUY":
        balances["USDT"] = balances.get("USDT", Decimal(0)) - quote
        balances[coin] = balances.get(coin, Decimal(0)) + quantity
    else:
        if order["type"] == "STOP_LOSS_LIMIT":
            locked[coin] = locked.get(coin, Decimal(0)) - quantity
        else:
            balances[coin] = balances.get(coin, Decimal(0)) - quantity
        balances["USDT"] = balances.get("USDT", Decimal(0)) + quote
    balances["BNB"] = balances.get("BNB", Decimal(0)) - fee_bnb
    order.update(status="FILLED", executedQty=str(quantity), cummulativeQuoteQty=str(quote),
                 fills=[{"price": str(at), "qty": str(quantity), "commission": str(fee_bnb),
                         "commissionAsset": "BNB"}], fee_bnb=str(fee_bnb))


def check_stops() -> None:
    for order in orders.values():
        if order["type"] == "STOP_LOSS_LIMIT" and order["status"] == "NEW":
            if price(order["symbol"]) <= Decimal(order["stopPrice"]):
                fill(order, Decimal(order["price"]))


def error(code: int, message: str, status: int = 400):
    return status, {"code": code, "msg": message}


def handle(method: str, path: str, query: dict[str, str]):
    symbol = query.get("symbol", "")
    if path == "/api/v3/time":
        return 200, {"serverTime": int(time.time() * 1000)}
    if path == "/api/v3/ticker/price":
        return 200, {"symbol": symbol, "price": str(price(symbol))}
    if path == "/api/v3/exchangeInfo":
        step, tick = RULES.get(symbol, ("0.001", "0.01"))
        return 200, {"symbols": [{"symbol": symbol, "orderTypes": ["LIMIT", "MARKET", "STOP_LOSS_LIMIT"],
                                  "filters": [{"filterType": "LOT_SIZE", "stepSize": step, "minQty": step},
                                              {"filterType": "PRICE_FILTER", "tickSize": tick},
                                              {"filterType": "NOTIONAL", "minNotional": "5"}]}]}
    if path == "/sapi/v1/account/apiRestrictions":
        return 200, {"ipRestrict": True, "enableReading": True, "enableSpotAndMarginTrading": True,
                     "enableWithdrawals": False, "enableInternalTransfer": False, "enableMargin": False,
                     "enableFutures": False, "permitsUniversalTransfer": False}
    if path == "/sapi/v1/bnbBurn":
        return 200, {"spotBNBBurn": True, "interestBNBBurn": False}
    if path == "/api/v3/account/commission":
        return 200, {"symbol": symbol, "standardCommission": {"maker": "0.001", "taker": "0.001"},
                     "discount": {"enabledForAccount": True, "enabledForSymbol": True, "discountAsset": "BNB",
                                  "discount": "0.75"}}
    with lock:
        check_stops()
        if path == "/api/v3/account":
            assets = sorted(set(balances) | set(locked))
            return 200, {"accountType": "SPOT", "canTrade": True, "balances": [
                {"asset": a, "free": str(balances.get(a, Decimal(0))), "locked": str(locked.get(a, Decimal(0)))}
                for a in assets if balances.get(a) or locked.get(a)]}
        if path == "/api/v3/openOrders":
            return 200, [o for o in orders.values() if o["status"] == "NEW" and (not symbol or o["symbol"] == symbol)]
        if path == "/api/v3/myTrades":
            order = orders.get(int(query["orderId"]))
            return 200, ([{"commission": order.get("fee_bnb", "0"), "commissionAsset": "BNB",
                           "price": order["fills"][0]["price"], "qty": order["executedQty"]}]
                         if order and order["status"] == "FILLED" else [])
        if path == "/api/v3/order" and method == "GET":
            if "origClientOrderId" in query:
                matches = [o for o in orders.values() if o.get("clientOrderId") == query["origClientOrderId"]]
                order = matches[-1] if matches else None
            else:
                order = orders.get(int(query["orderId"]))
            return (200, order) if order else error(-2013, "Order does not exist.")
        if path == "/api/v3/order" and method == "DELETE":
            order = orders.get(int(query["orderId"]))
            if not order or order["status"] != "NEW":
                return error(-2011, "Unknown order sent.")
            order["status"] = "CANCELED"
            coin = asset(order["symbol"])
            quantity = Decimal(order["origQty"])
            locked[coin] = locked.get(coin, Decimal(0)) - quantity
            balances[coin] = balances.get(coin, Decimal(0)) + quantity
            return 200, order
        if path == "/api/v3/order" and method == "POST":
            return place(query)
    return error(-1121, f"Fake Binance does not handle {method} {path}", 404)


def place(query: dict[str, str]):
    symbol, side, kind = query["symbol"], query["side"], query["type"]
    now = price(symbol)
    next_id[0] += 1
    order = {"orderId": next_id[0], "clientOrderId": query.get("newClientOrderId"), "symbol": symbol,
             "side": side, "type": kind, "status": "NEW", "executedQty": "0", "cummulativeQuoteQty": "0",
             "transactTime": int(time.time() * 1000)}
    coin = asset(symbol)
    if kind == "MARKET" and side == "BUY":
        spend = Decimal(query["quoteOrderQty"])
        if spend > balances.get("USDT", Decimal(0)):
            return error(-2010, "Account has insufficient balance for requested action.")
        step = Decimal(RULES.get(symbol, ("0.001",))[0])
        order["origQty"] = str((spend / now / step).to_integral_value(rounding="ROUND_DOWN") * step)
        fill(order, now)
    elif kind == "MARKET" and side == "SELL":
        quantity = Decimal(query["quantity"])
        if quantity > balances.get(coin, Decimal(0)):
            return error(-2010, "Account has insufficient balance for requested action.")
        order["origQty"] = str(quantity)
        fill(order, now)
    elif kind == "STOP_LOSS_LIMIT":
        quantity = Decimal(query["quantity"])
        if quantity > balances.get(coin, Decimal(0)):
            return error(-2010, "Account has insufficient balance for requested action.")
        balances[coin] -= quantity
        locked[coin] = locked.get(coin, Decimal(0)) + quantity
        order.update(origQty=str(quantity), stopPrice=query["stopPrice"], price=query["price"])
    else:
        return error(-1116, "Invalid orderType.")
    orders[order["orderId"]] = order
    return 200, order


class Handler(BaseHTTPRequestHandler):
    def _serve(self, method: str) -> None:
        url = urlparse(self.path)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode() if method == "POST" else ""
        query = {k: v[-1] for k, v in parse_qs(url.query + ("&" + body if body else "")).items()}
        try:
            status, payload = handle(method, url.path, query)
        except Exception as exc:  # keep the fake alive and say what broke
            status, payload = 500, {"code": -1000, "msg": f"fake binance error: {exc}"}
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")

    def do_DELETE(self):
        self._serve("DELETE")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Fake Binance on :{PORT} with ${START_USDT} USDT and {START_BNB} BNB", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
