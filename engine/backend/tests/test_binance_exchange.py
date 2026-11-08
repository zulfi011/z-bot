from decimal import Decimal

import pytest

from app.services.binance_client import BinanceClient, BinanceError
from app.services.binance_exchange import BinanceExchange, SymbolRules

INFO = {"symbols": [{"symbol": "ETHUSDT", "orderTypes": ["LIMIT", "MARKET", "STOP_LOSS_LIMIT"], "filters": [
    {"filterType": "LOT_SIZE", "stepSize": "0.00010000", "minQty": "0.00010000"},
    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
    {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]}]}


def exchange(monkeypatch, live=True, response=None, error=None):
    api = BinanceClient("key", "secret")
    sent = []

    def fake_request(method, path, params=None, signed=False):
        if path == "/api/v3/exchangeInfo":
            return INFO
        sent.append((method, path, dict(params or {})))
        if error:
            raise error
        return response or {}

    monkeypatch.setattr(api, "_request", fake_request)
    monkeypatch.setattr(api, "_synchronize_clock", lambda: None)
    return BinanceExchange(api, live=live), sent


def test_rules_are_read_from_binance(monkeypatch):
    market, _ = exchange(monkeypatch)
    rules = market.rules("ETHUSDT")
    assert rules.step_size == Decimal("0.0001") and rules.minimum_notional == Decimal("5")
    assert rules.round_quantity(Decimal("0.0398765")) == Decimal("0.0398")
    assert rules.round_price(Decimal("2500.678")) == Decimal("2500.67")
    assert rules.stop_loss_limit


def test_small_orders_are_refused_before_they_are_sent():
    rules = SymbolRules("ETHUSDT", Decimal("0.0001"), Decimal("0.01"), Decimal("0.0001"), Decimal("5"), True)
    assert rules.rejects_buy(Decimal("3")) and "smallest" in rules.rejects_buy(Decimal("3"))
    assert rules.rejects_buy(Decimal("100")) is None
    assert rules.rejects_sell(Decimal("0.00001"), Decimal("2500")) is not None
    assert rules.rejects_sell(Decimal("0.04"), Decimal("2500")) is None


def test_market_buy_spends_an_exact_dollar_amount(monkeypatch):
    market, sent = exchange(monkeypatch, response={"orderId": 7, "executedQty": "0.0397",
                                                   "cummulativeQuoteQty": "99.99",
                                                   "fills": [{"commission": "0.00007", "commissionAsset": "BNB"}]})
    result = market.market_buy("ETHUSDT", Decimal("100"))
    assert sent[0][2]["quoteOrderQty"] == "100" and sent[0][2]["type"] == "MARKET"
    assert result.ok and result.exchange_order_id == "7"
    assert result.filled_quantity == Decimal("0.0397")
    assert result.average_price.quantize(Decimal("0.01")) == Decimal("2518.64")
    assert result.commission() == (Decimal("0.00007"), "BNB")


def test_decision_quote_reads_the_best_bid_and_ask(monkeypatch):
    market, sent = exchange(monkeypatch, response={"bidPrice": "2518.10", "askPrice": "2518.20"})
    assert market.best_bid_ask("ETHUSDT") == (Decimal("2518.10"), Decimal("2518.20"))
    assert sent == [("GET", "/api/v3/ticker/bookTicker", {"symbol": "ETHUSDT"})]


def test_protective_stop_sits_below_the_trigger_and_fits_the_tick(monkeypatch):
    market, sent = exchange(monkeypatch, response={"orderId": 11})
    market.protective_stop("ETHUSDT", Decimal("0.039789"), Decimal("2415.4567"))
    params = sent[0][2]
    assert params["type"] == "STOP_LOSS_LIMIT" and params["side"] == "SELL"
    assert params["quantity"] == "0.0397" and params["stopPrice"] == "2415.45"
    assert Decimal(params["price"]) < Decimal(params["stopPrice"])


def test_shadow_mode_prepares_the_order_but_sends_nothing(monkeypatch):
    market, sent = exchange(monkeypatch, live=False)
    result = market.market_buy("ETHUSDT", Decimal("100"))
    assert sent == [] and result.sent is False and result.ok
    assert result.request["quoteOrderQty"] == "100"


def test_a_rejected_order_is_reported_not_raised(monkeypatch):
    market, _ = exchange(monkeypatch, error=BinanceError(-2010, "Account has insufficient balance"))
    result = market.market_buy("ETHUSDT", Decimal("100"))
    assert result.ok is False and "not enough balance" in result.error
