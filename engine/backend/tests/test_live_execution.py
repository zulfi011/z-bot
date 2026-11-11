"""The live engine's decisions, tested without a database or a real exchange.

The fake connection answers each query by looking at its SQL, and records every write, so a test can assert what
the engine would put in the ledger and what it would send to Binance.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.paper_execution import Candle, Position
from app.services import live_execution_service as live
from app.services.binance_exchange import OrderResult, SymbolRules

NOW = datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc)
STRATEGY = {
    "strategy_id": "sol-3m",
    "market": {"symbol": "SOLUSDT"},
    "portfolio": {"minimum_lot_size_usd": 10, "maximum_lot_size_usd": 100000, "maximum_lots_per_coin": 20},
    "execution_model": {"usdt_fee_bps_per_side": 10, "bnb_fee_bps_per_side": 7.5, "slippage_bps_per_side": 0},
    "exit": {"protective_stop_pct_from_entry_fill": 2, "maximum_hold_minutes": None,
             "trailing_stop": {"activation_pct_from_entry_fill": 1.251, "giveback_of_open_profit_pct": 12}},
}


class Result:
    """Whatever a single query returned, in the shapes SQLAlchemy offers."""

    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return Result(self.value or [])

    def mappings(self):
        return self

    def one_or_none(self):
        return self.value

    def all(self):
        return self.value or []


class FakeConnection:
    """Answers SELECTs from `answers` (first matching SQL fragment wins) and remembers every write."""

    def __init__(self, **answers):
        self.answers = {
            "FROM engine_state": {"trading_mode": "shadow", "daily_loss_limit_usd": "25",
                                  "maximum_open_value_usd": "0", "pot_lots": 3, "pot_lot_size_usd": "100"},
            "SELECT dip_enabled, breakout_enabled": {"dip_enabled": True, "breakout_enabled": True,
                                                      "pullback_enabled": True, "pyramid_enabled": False},
            "trading_enabled FROM coin_allocations": True,
            # every way in shares one set of lots, so there is a single number to count
            "count(*) FROM paper_positions": 0,
            "sum(allocation_usd),0) FROM paper_positions WHERE symbol": Decimal("0"),
            "sum(allocation_usd),0) FROM paper_positions\n": Decimal("0"),
            "FROM paper_trades": Decimal("0"),
            "FROM control_requests": [],
            "FROM candles_1m": Decimal("600"),
            **answers,
        }
        self.writes: list[tuple[str, dict]] = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        if sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            self.writes.append((sql, dict(parameters or {})))
            return Result(None)
        for fragment, answer in self.answers.items():
            if fragment in sql:
                return Result(answer)
        return Result(None)

    def written(self, *fragments) -> dict:
        """Parameters of the single write whose SQL mentions all fragments."""
        matches = [params for sql, params in self.writes if all(f in sql for f in fragments)]
        assert len(matches) == 1, f"expected one write matching {fragments}, found {len(matches)}"
        return matches[0]

    def wrote(self, *fragments) -> bool:
        return any(all(f in sql for f in fragments) for sql, _ in self.writes)


class FakeExchange:
    """Records orders instead of sending them; `live` mirrors the real exchange's flag."""

    def __init__(self, live=False, buy=None, sell=None, stop=None, status=None):
        self.live = live
        self.calls: list[tuple] = []
        self._buy, self._sell, self._stop, self._status = buy, sell, stop, status or {}

    def rules(self, symbol):
        return SymbolRules(symbol, Decimal("0.01"), Decimal("0.01"), Decimal("0.01"), Decimal("5"), True)

    def market_buy(self, symbol, quote_amount, client_order_id=None):
        self.calls.append(("buy", symbol, quote_amount))
        return self._buy or OrderResult(sent=False, client_order_id="c1", request={}, response={"shadow": True})

    def market_sell(self, symbol, amount, client_order_id=None):
        self.calls.append(("sell", symbol, amount))
        return self._sell or OrderResult(sent=False, client_order_id="c2", request={}, response={"shadow": True})

    def stop_trigger(self, symbol, stop_price):
        return self.rules(symbol).round_price(stop_price) if self.live else stop_price

    def protective_stop(self, symbol, amount, stop_price, client_order_id=None):
        self.calls.append(("stop", symbol, amount, stop_price))
        return self._stop or OrderResult(sent=False, client_order_id="c3", request={}, response={"shadow": True})

    def cancel(self, symbol, order_id):
        self.calls.append(("cancel", symbol, order_id))
        return OrderResult(sent=True, client_order_id="c4", request={}, response={"orderId": order_id})

    def order_status(self, symbol, order_id):
        self.calls.append(("status", symbol, order_id))
        return self._status

    def my_trades(self, symbol, order_id):
        return [{"commission": "0.01", "commissionAsset": "BNB"}]


def service(exchange=None, balances=None):
    engine = live.LiveExecutionService.__new__(live.LiveExecutionService)
    engine.engine = None
    engine.exchange = exchange or FakeExchange()
    engine.coins = {"SOLUSDT": live.CoinSetup.from_strategy(STRATEGY)}
    engine._balances = (float("inf"), balances or {}, {})
    engine._tickers = {}
    engine._balances_unknown = False
    engine._last_block_reason = None
    if balances is not None:
        engine.balances = lambda refresh=False: balances
    return engine


def candle(close="200", high=None, low=None, at=NOW):
    value = Decimal(close)
    return Candle(open_time=at, open=value, high=Decimal(high or close), low=Decimal(low or close), close=value)


def position(**overrides):
    # Held for half an hour up to the real clock, because the ledger stamps the exit with now().
    defaults = dict(position_id="position:s1", entry_time=datetime.now(timezone.utc) - timedelta(minutes=30), raw_entry_price=Decimal("200"),
                    entry_fill_price=Decimal("200"), quantity=Decimal("0.5"), allocation_usd=Decimal("100"),
                    entry_fee_usd=Decimal("0.1"), entry_fee_asset="USDT", symbol="SOLUSDT")
    return Position(**{**defaults, **overrides})


ROW = {"stop_order_id": None, "entry_source": "signal"}


# ---------------------------------------------------------------- entry gating
@pytest.mark.parametrize("answers,expected", [
    ({"trading_enabled FROM coin_allocations": None}, "switched off"),        # a coin never switched on
    ({"trading_enabled FROM coin_allocations": False}, "switched off"),
    ({"FROM engine_state": {"trading_mode": "off"}}, "All trading is stopped"),
    # the count is every coin's open lots: the pot is shared, so other coins can fill it
    ({"count(*) FROM paper_positions": 3}, "All 3 shared lots are open"),
    ({"FROM engine_state": {"trading_mode": "shadow", "pot_lots": 5, "pot_lot_size_usd": "100"}, "count(*) FROM paper_positions": 5},
     "All 5 shared lots are open"),
    ({"SELECT dip_enabled, breakout_enabled": {"dip_enabled": True, "breakout_enabled": True, "pullback_enabled": False,
                                               "pyramid_enabled": False}}, "pullback entry is switched off"),
    ({"FROM engine_state": {"trading_mode": "shadow", "maximum_open_value_usd": "150", "pot_lots": 3,
                            "pot_lot_size_usd": "100"},
      "sum(allocation_usd),0) FROM paper_positions": Decimal("100")}, "limit on money in open trades"),
    ({"FROM paper_trades": Decimal("-30")}, "loss limit"),
])
def test_entries_are_blocked_with_a_reason_the_dashboard_can_show(answers, expected):
    source = "pullback" if "pullback" in expected else "signal"
    allowed, reason, _ = service()._entry_allowed(FakeConnection(**answers), live.CoinSetup.from_strategy(STRATEGY),
                                                  source)
    assert not allowed and expected in reason


def test_the_pot_lot_size_is_what_every_coin_buys():
    connection = FakeConnection(**{"FROM engine_state": {"trading_mode": "shadow", "pot_lots": 5,
                                                         "pot_lot_size_usd": "120"},
                                   "count(*) FROM paper_positions": 4})
    allowed, reason, lot = service()._entry_allowed(connection, live.CoinSetup.from_strategy(STRATEGY))
    assert allowed and reason is None and lot == Decimal("120")


def test_a_free_slot_with_money_is_allowed():
    allowed, reason, lot = service()._entry_allowed(FakeConnection(), live.CoinSetup.from_strategy(STRATEGY))
    assert allowed and reason is None and lot == Decimal("100")


def test_live_entries_need_some_usdt_in_the_wallet():
    engine = service(exchange=FakeExchange(live=True), balances={"USDT": Decimal("0")})
    allowed, reason, _ = engine._entry_allowed(FakeConnection(), live.CoinSetup.from_strategy(STRATEGY))
    assert not allowed and "$0.00 free USDT" in reason


# ---------------------------------------------------------------- buying
def test_a_shadow_buy_is_recorded_with_a_stop_and_never_sent():
    engine, connection = service(), FakeConnection()
    coin = engine.coins["SOLUSDT"]
    assert engine._buy(connection, coin, candle("200"), signal_id="s1") == "position:s1"
    opened = connection.written("INSERT INTO paper_positions")
    assert opened["cost"] == Decimal("100.00") and opened["qty"] == Decimal("0.500000000000")
    assert opened["fill"] == Decimal("200.0000000000") and opened["fee"] == Decimal("0.10")
    order = connection.written("INSERT INTO paper_orders", "'buy'")
    assert order["status"] == "shadow"
    stop = engine.exchange.calls[-1]
    assert stop[0] == "stop" and stop[3] == Decimal("196.000")  # 2% under the fill
    assert connection.wrote("UPDATE paper_positions SET stop_order_id")


def test_a_live_buy_uses_the_real_fill_and_a_bnb_fee_leaves_the_quantity_whole():
    filled = OrderResult(sent=True, client_order_id="c1", request={},
                         response={"orderId": 11, "executedQty": "0.4970", "cummulativeQuoteQty": "99.99",
                                   "fills": [{"commission": "0.0012", "commissionAsset": "BNB"}]})
    engine = service(exchange=FakeExchange(live=True, buy=filled), balances={"USDT": Decimal("500")})
    connection = FakeConnection(**{"FROM candles_1m": Decimal("900")})  # BNB price for the fee
    engine._buy(connection, engine.coins["SOLUSDT"], candle("201"), signal_id="s1")
    opened = connection.written("INSERT INTO paper_positions")
    assert opened["qty"] == Decimal("0.497000000000")            # fee paid in BNB, all the coin stays sellable
    assert opened["asset"] == "BNB" and opened["fee"] == Decimal("1.08")  # 0.0012 BNB at $900
    assert opened["order_id"] == "11"


def test_a_fee_taken_in_the_coin_reduces_what_can_be_sold():
    filled = OrderResult(sent=True, client_order_id="c1", request={},
                         response={"orderId": 12, "executedQty": "0.5000", "cummulativeQuoteQty": "100.00",
                                   "fills": [{"commission": "0.0005", "commissionAsset": "SOL"}]})
    engine = service(exchange=FakeExchange(live=True, buy=filled), balances={"USDT": Decimal("500")})
    connection = FakeConnection()
    engine._buy(connection, engine.coins["SOLUSDT"], candle("200"), signal_id="s1")
    assert connection.written("INSERT INTO paper_positions")["qty"] == Decimal("0.499500000000")


def test_a_rejected_buy_leaves_no_position_and_says_why():
    failed = OrderResult(sent=True, client_order_id="c1", request={}, error="Binance refused the order",
                         response={"code": -2010})
    engine = service(exchange=FakeExchange(live=True, buy=failed), balances={"USDT": Decimal("500")})
    connection = FakeConnection()
    assert engine._buy(connection, engine.coins["SOLUSDT"], candle("200"), signal_id="s1") is None
    assert not connection.wrote("INSERT INTO paper_positions")
    assert connection.wrote("INSERT INTO system_events")


def test_execution_observation_calculates_fee_impact_and_reference_slippage():
    connection = FakeConnection()
    live.LiveExecutionService._record_execution_observation(
        connection, "ETHUSDT", "position:s1", "buy", "filled", NOW, NOW, NOW,
        Decimal("199"), Decimal("200"), Decimal("198"), Decimal("201"), 125.0,
        Decimal("0.075"), "BNB", Decimal("100"), "client-1", "exchange-1", False, None, {},
    )
    observation = connection.written("INSERT INTO execution_observations")
    assert observation["fee_rate"] == Decimal("7.50000")
    assert observation["impact"] == Decimal("50.000")
    assert observation["slippage"] > Decimal("151")


def test_a_blocked_signal_is_marked_instead_of_bought():
    engine = service()
    connection = FakeConnection(**{"count(*) FROM paper_positions": 3})
    assert engine._buy(connection, engine.coins["SOLUSDT"], candle(), signal_id="s1") is None
    assert "All 3 shared lots are open" in connection.written("UPDATE signals")["reason"]


def test_a_lot_below_binances_minimum_is_never_sent():
    engine = service(exchange=FakeExchange(live=True), balances={"USDT": Decimal("500")})
    connection = FakeConnection(**{"FROM engine_state": {"trading_mode": "live", "pot_lots": 1,
                                                         "pot_lot_size_usd": "4"}})
    assert engine._buy(connection, engine.coins["SOLUSDT"], candle(), signal_id="s1") is None
    assert engine.exchange.calls == []


def test_an_unprotected_lot_is_reported_loudly():
    stop = OrderResult(sent=True, client_order_id="c3", request={}, error="Binance refused the stop", response={})
    engine = service(exchange=FakeExchange(live=True, buy=OrderResult(
        sent=True, client_order_id="c1", request={},
        response={"orderId": 13, "executedQty": "0.5", "cummulativeQuoteQty": "100", "fills": []}), stop=stop),
        balances={"USDT": Decimal("500")})
    connection = FakeConnection()
    engine._buy(connection, engine.coins["SOLUSDT"], candle(), signal_id="s1")
    events = [params for sql, params in connection.writes if "system_events" in sql]
    assert any("stop_order_failed" in str(params.values()) for params in events)


# ---------------------------------------------------------------- selling
def test_a_shadow_sell_books_the_profit_after_fees():
    engine, connection = service(), FakeConnection()
    engine._sell(connection, engine.coins["SOLUSDT"], position(), ROW, "trailing_stop", candle("210"))
    closed = connection.written("UPDATE paper_positions SET status='closed'")
    # 0.5 SOL at $210 = $105, minus the $0.105 exit fee, minus the $100 lot.
    assert closed["received"] == Decimal("105") and closed["pnl"] == Decimal("4.895")
    assert closed["reason"] == "trailing_stop" and closed["sold"] == Decimal("0.500000000000")
    trade = connection.written("INSERT INTO paper_trades")
    assert trade["pnl"] == Decimal("4.895") and trade["duration"] == 30 and trade["symbol"] == "SOLUSDT"


def test_selling_cancels_the_parked_stop_first_and_only_sells_what_binance_holds():
    sold = OrderResult(sent=True, client_order_id="c2", request={},
                       response={"orderId": 21, "executedQty": "0.45", "cummulativeQuoteQty": "94.50",
                                 "fills": [{"commission": "0.0945", "commissionAsset": "USDT"}]})
    engine = service(exchange=FakeExchange(live=True, sell=sold), balances={"SOL": Decimal("0.45")})
    connection = FakeConnection()
    engine._sell(connection, engine.coins["SOLUSDT"], position(), {**ROW, "stop_order_id": "99"}, "manual_close",
                 candle("210"))
    assert engine.exchange.calls[0] == ("cancel", "SOLUSDT", "99")
    assert engine.exchange.calls[1] == ("sell", "SOLUSDT", Decimal("0.45"))  # clamped to the real balance
    closed = connection.written("UPDATE paper_positions SET status='closed'")
    assert closed["received"] == Decimal("94.5") and closed["pnl"] == Decimal("-5.5945")


def test_a_failed_sell_keeps_the_position_open():
    failed = OrderResult(sent=True, client_order_id="c2", request={}, error="Binance refused the order", response={})
    engine = service(exchange=FakeExchange(live=True, sell=failed), balances={"SOL": Decimal("0.5")})
    connection = FakeConnection()
    engine._sell(connection, engine.coins["SOLUSDT"], position(), ROW, "trailing_stop", candle("210"))
    assert not connection.wrote("UPDATE paper_positions SET status='closed'")
    assert connection.wrote("INSERT INTO system_events")


def test_a_stop_binance_filled_itself_is_recorded_as_a_closed_trade():
    engine = service(exchange=FakeExchange(live=True, status={"status": "FILLED", "orderId": 31,
                                                              "executedQty": "0.5",
                                                              "cummulativeQuoteQty": "98.00"}),
                     balances={"SOL": Decimal("0")})
    connection = FakeConnection(**{"FROM candles_1m": Decimal("900")})
    assert engine._stop_order_filled(connection, engine.coins["SOLUSDT"], position(),
                                     {**ROW, "stop_order_id": "31"}) is True
    closed = connection.written("UPDATE paper_positions SET status='closed'")
    assert closed["reason"] == "protective_stop" and closed["received"] == Decimal("98.00")
    assert closed["asset"] == "BNB"  # commission read back from myTrades


def test_a_stop_that_is_still_waiting_changes_nothing():
    engine = service(exchange=FakeExchange(live=True, status={"status": "NEW", "orderId": 31}),
                     balances={"SOL": Decimal("0.5")})
    connection = FakeConnection()
    assert engine._stop_order_filled(connection, engine.coins["SOLUSDT"], position(),
                                     {**ROW, "stop_order_id": "31"}) is False
    assert connection.writes == []


# ---------------------------------------------------------------- fee pricing
def test_a_bnb_fee_is_valued_from_binance_when_no_candle_is_stored():
    engine = service()
    engine.exchange.client = _Client({"price": "600"})
    connection = FakeConnection(**{"FROM candles_1m": None})
    assert engine._fee_in_usd(connection, Decimal("0.002"), "BNB", "SOLUSDT") == Decimal("1.2")


def test_a_fee_that_cannot_be_priced_is_recorded_loudly_not_silently():
    engine = service()
    engine.exchange.client = _Client(None)
    connection = FakeConnection(**{"FROM candles_1m": None})
    assert engine._fee_in_usd(connection, Decimal("0.002"), "BNB", "SOLUSDT") == Decimal("0")
    events = [params for sql, params in connection.writes if "system_events" in sql]
    assert any("fee_value_unknown" in str(params.values()) for params in events)


class _Client:
    """Binance's ticker endpoint: a price, or an outage."""

    def __init__(self, payload):
        self.payload = payload

    def _request(self, method, path, params=None, signed=False):
        if self.payload is None:
            from app.services.binance_client import BinanceError
            raise BinanceError(None, "Could not reach Binance")
        return self.payload


# ---------------------------------------------------------------- lot affordability
def test_the_last_coin_to_buy_takes_whatever_the_pot_has_left():
    assert live.affordable_lot(Decimal("100"), Decimal("250")) == Decimal("100")
    assert live.affordable_lot(Decimal("100"), Decimal("98")) == Decimal("98.00")
    assert live.affordable_lot(Decimal("150"), Decimal("1.009")) == Decimal("1.00")
    assert live.affordable_lot(Decimal("100"), Decimal("0.004")) is None      # nothing left at all


def test_a_lot_shrunk_by_earlier_losses_still_buys():
    engine = service(exchange=FakeExchange(live=True), balances={"USDT": Decimal("40")})
    allowed, reason, lot = engine._entry_allowed(FakeConnection(), live.CoinSetup.from_strategy(STRATEGY))
    assert allowed and lot == Decimal("40.00")


def test_a_failed_balance_read_does_not_record_a_zero_wallet():
    from unittest.mock import MagicMock
    from app.services.binance_client import BinanceError
    engine = service()
    engine._balances = None
    engine.exchange.client = MagicMock()
    engine.exchange.client.account.side_effect = BinanceError(None, "Could not reach Binance")
    engine.engine = MagicMock()
    connection = engine.engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one_or_none.return_value = {"trading_mode": "live"}
    engine._write_snapshot()
    written = [str(call.args[0]) for call in connection.execute.call_args_list if call.args]
    assert not any("account_snapshots" in sql for sql in written)   # no snapshot written for this minute
