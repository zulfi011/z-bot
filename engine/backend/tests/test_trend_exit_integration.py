"""ETH's Mode A exit, end to end through LiveExecutionService.

The domain tests prove the rule; this proves the wiring around it — that the trend line is computed from
stored candles, that a lot opened in a clean uptrend is marked Mode A, that it ignores the giveback level
that would have closed it, and that the first close below the line sells at the NEXT minute's open. It runs
against a real throwaway database with Binance faked at the HTTP layer, like the other integration tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from app.core.strategy import load_strategies
from app.services.binance_client import BinanceClient, BinanceError
from app.services.binance_exchange import BinanceExchange
from app.services.live_execution_service import LiveExecutionService

BASE_URL = os.environ.get("INTEGRATION_DATABASE_URL",
                          "postgresql+psycopg://paperbot:paperbot_local@db:5432/papertrading")
SYMBOL = "ETHUSDT"
MINUTE = timedelta(minutes=1)
START = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)   # outside the 06-12 UTC blocked window

EXCHANGE_INFO = {"symbols": [{"symbol": SYMBOL, "orderTypes": ["LIMIT", "MARKET", "STOP_LOSS_LIMIT"], "filters": [
    {"filterType": "LOT_SIZE", "stepSize": "0.00010000", "minQty": "0.00010000"},
    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
    {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]}]}


class FakeBinance:
    def __init__(self) -> None:
        self.price = Decimal("200")
        self.usdt = Decimal("1000")
        self.coin = Decimal("0")
        self.locked = Decimal("0")
        self.orders: dict[str, dict] = {}
        self._next_id = 5000

    def request(self, method: str, path: str, params=None, signed=False):
        params = dict(params or {})
        if path == "/api/v3/time":
            return {"serverTime": int(datetime.now(timezone.utc).timestamp() * 1000)}
        if path == "/api/v3/exchangeInfo":
            return EXCHANGE_INFO
        if path == "/api/v3/ticker/bookTicker":
            return {"symbol": params["symbol"], "bidPrice": str(self.price), "askPrice": str(self.price)}
        if path == "/api/v3/ticker/price":
            return {"symbol": params["symbol"], "price": "600" if params["symbol"] == "BNBUSDT" else str(self.price)}
        if path == "/api/v3/account":
            return {"accountType": "SPOT", "canTrade": True, "balances": [
                {"asset": "USDT", "free": str(self.usdt), "locked": "0"},
                {"asset": "ETH", "free": str(self.coin), "locked": str(self.locked)},
                {"asset": "BNB", "free": "0.5", "locked": "0"}]}
        if path == "/api/v3/order" and method == "POST":
            return self._place(params)
        if path == "/api/v3/order" and method == "GET":
            if "origClientOrderId" in params:
                found = [o for o in self.orders.values() if o["clientOrderId"] == params["origClientOrderId"]]
                if not found:
                    raise BinanceError(-2013, "Order does not exist.")
                return found[-1]
            return self.orders[str(params["orderId"])]
        if path == "/api/v3/order" and method == "DELETE":
            order = self.orders[str(params["orderId"])]
            order["status"] = "CANCELED"
            self.locked -= Decimal(order["origQty"])
            self.coin += Decimal(order["origQty"])
            return order
        if path == "/api/v3/myTrades":
            return []
        raise AssertionError(f"unexpected Binance call {method} {path}")

    def _place(self, params):
        self._next_id += 1
        order_id = self._next_id
        order = {"orderId": order_id, "clientOrderId": params.get("newClientOrderId", str(order_id)),
                 "symbol": params["symbol"], "side": params["side"], "type": params["type"],
                 "status": "NEW", "executedQty": "0", "cummulativeQuoteQty": "0",
                 "origQty": params.get("quantity", "0"), "fills": []}
        if params["type"] == "STOP_LOSS_LIMIT":
            order["stopPrice"] = params.get("stopPrice")
            self.locked += Decimal(params["quantity"])
            self.coin -= Decimal(params["quantity"])
        elif params["side"] == "BUY":
            spend = Decimal(params["quoteOrderQty"])
            quantity = (spend / self.price).quantize(Decimal("0.0001"))
            self.usdt -= spend
            self.coin += quantity
            order.update(status="FILLED", executedQty=str(quantity), cummulativeQuoteQty=str(spend),
                         origQty=str(quantity),
                         fills=[{"price": str(self.price), "qty": str(quantity),
                                 "commission": str(spend / Decimal("600") * Decimal("0.00075")),
                                 "commissionAsset": "BNB"}])
        else:
            quantity = Decimal(params["quantity"])
            received = quantity * self.price
            self.usdt += received
            self.coin -= quantity
            order.update(status="FILLED", executedQty=str(quantity), cummulativeQuoteQty=str(received),
                         fills=[{"price": str(self.price), "qty": str(quantity),
                                 "commission": str(received / Decimal("600") * Decimal("0.00075")),
                                 "commissionAsset": "BNB"}])
        self.orders[str(order_id)] = order
        return order


@pytest.fixture(scope="module")
def database():
    admin_url = BASE_URL.rsplit("/", 1)[0] + "/postgres"
    name = f"zbot_trend_{uuid.uuid4().hex[:8]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as error:
        pytest.skip(f"no PostgreSQL for the integration test ({error})")
    url = BASE_URL.rsplit("/", 1)[0] + f"/{name}"
    migrated = subprocess.run(["alembic", "upgrade", "head"], cwd="/app" if os.path.isdir("/app/migrations") else ".",
                              env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True)
    assert migrated.returncode == 0, migrated.stderr
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


def build_world(database, uptrend: bool, live: bool = True):
    binance = FakeBinance()
    client = BinanceClient("key", "secret")
    client._request = binance.request  # type: ignore[method-assign]
    execution = LiveExecutionService(database, {SYMBOL: load_strategies()[SYMBOL]},
                                     BinanceExchange(client, live=live))
    a7, a15, a30 = (Decimal("210"), Decimal("205"), Decimal("200")) if uptrend else \
                   (Decimal("195"), Decimal("205"), Decimal("210"))
    with database.begin() as connection:
        for table in ("paper_trades", "paper_orders", "paper_positions", "signals", "touch_episodes",
                      "candles_1m", "exchange_events", "monitoring_alerts", "account_snapshots",
                      "system_events", "control_requests", "engine_state", "daily_averages"):
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(
            text("""INSERT INTO coin_allocations (symbol, trading_enabled, updated_at)
                    VALUES (:s, true, now())
                    ON CONFLICT (symbol) DO UPDATE SET trading_enabled=true"""),
            {"s": SYMBOL})
        connection.execute(
            text("""INSERT INTO engine_state (key, value) VALUES ('account_settings', CAST(:v AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value=CAST(:v AS jsonb)"""),
            {"v": json.dumps({"trading_mode": "live", "daily_loss_limit_usd": "0",
                              "maximum_open_value_usd": "0", "pot_lots": 1, "pot_lot_size_usd": "100"})})
        connection.execute(
            text("""INSERT INTO daily_averages (symbol, effective_at, completed_through, average_7d, average_15d,
                                                average_30d, signal_average_days, signal_average)
                    VALUES (:s, :at, :day, :a7, :a15, :a30, 7, :a7)"""),
            {"s": SYMBOL, "at": START.replace(hour=0, minute=0), "day": START.date() - timedelta(days=1),
             "a7": a7, "a15": a15, "a30": a30})
    return execution, binance, database


def candle(engine, at, price, high=None, low=None, open_=None) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO candles_1m (symbol, open_time, open, high, low, close, volume, source)
                    VALUES (:s, :t, :o, :h, :l, :c, 1, 'test') ON CONFLICT (symbol, open_time) DO NOTHING"""),
            {"s": SYMBOL, "t": at, "o": open_ or price, "h": high or price, "l": low or price, "c": price})


def confirmed_signal(engine, at, strategy_id) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO touch_episodes (episode_id, strategy_id, symbol, touch_time, average_value, status)
                    VALUES ('e1', :strategy, :s, :t, 200, 'confirmed')"""),
            {"strategy": strategy_id, "s": SYMBOL, "t": at})
        connection.execute(
            text("""INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, entry_time, status)
                    VALUES ('s1', 'e1', :strategy, :t, :t, 'confirmed')"""),
            {"strategy": strategy_id, "t": at})


def rows(engine, sql, **params):
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), params).mappings().all()]


def open_a_lot(world):
    """Buy one ETH lot at $200 and climb to $210 so the trail arms with a peak of 210."""
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)
    for index, price in enumerate([Decimal("204"), Decimal("208"), Decimal("210")], start=1):
        binance.price = price
        candle(engine, entry_time + index * MINUTE, price)
    execution.synchronize(SYMBOL)
    return entry_time


def test_a_lot_opened_in_an_uptrend_rides_the_trend_line(database):
    world = build_world(database, uptrend=True)
    execution, binance, engine = world
    entry_time = open_a_lot(world)

    position = rows(engine, "SELECT * FROM paper_positions")[0]
    assert position["trend_exit_active"] is True, "opened in a clean uptrend, so it must be a Mode A lot"
    assert position["trailing_active"] is True and position["peak_price"] == Decimal("210.0000000000")
    # It armed in the same minute it was bought, so its stop has already been lifted from -4.5% ($191) to
    # break even plus costs - the lot can no longer come back and finish negative.
    assert position["stop_price"] == Decimal("200.3800000000")

    # Mode B would give back 30% of the $10 gain and sell at 207. Mode A holds: 205 is still above the line.
    binance.price = Decimal("205")
    candle(engine, entry_time + 4 * MINUTE, Decimal("205"), high=Decimal("210"), low=Decimal("205"))
    execution.synchronize(SYMBOL)
    assert rows(engine, "SELECT status FROM paper_positions")[0]["status"] == "open", \
        "Mode A must ignore the giveback level"

    # Coming back to the entry now meets the break-even floor before it ever reaches the line. In live mode the
    # order Binance holds is the one that sells, so the bot leaves the lot alone and waits for that fill.
    binance.price = Decimal("199")
    candle(engine, entry_time + 5 * MINUTE, Decimal("199"), high=Decimal("205"), low=Decimal("199"))
    execution.synchronize(SYMBOL)
    waiting = rows(engine, "SELECT status, stop_price FROM paper_positions")[0]
    assert waiting["status"] == "open" and waiting["stop_price"] == Decimal("200.3800000000")


def test_the_break_even_floor_is_parked_on_binance_when_the_lot_arms(database):
    """The other half of Mode A: arming lifts the stop to break even, on Binance as well as in the database."""
    world = build_world(database, uptrend=True)
    execution, binance, engine = world
    open_a_lot(world)
    stored = rows(engine, "SELECT stop_price, stop_order_id FROM paper_positions")[0]
    assert stored["stop_price"] == Decimal("200.3800000000"), "lifted from the -4.5% stop at $191"
    parked = binance.orders[str(stored["stop_order_id"])]
    assert parked["type"] == "STOP_LOSS_LIMIT" and parked["status"] == "NEW"
    assert Decimal(parked["stopPrice"]) == Decimal("200.38"), "Binance holds the floor, not the old stop"
    assert [o["status"] for o in binance.orders.values() if o["type"] == "STOP_LOSS_LIMIT"] == ["CANCELED", "NEW"], \
        "the first stop was cancelled before the new one went on"


def test_the_break_even_floor_sells_the_lot_when_nothing_is_parked(database):
    """In shadow mode there is no order on Binance, so the bot itself sells at the floor."""
    world = build_world(database, uptrend=True, live=False)
    execution, binance, engine = world
    entry_time = open_a_lot(world)
    assert rows(engine, "SELECT stop_price FROM paper_positions")[0]["stop_price"] == Decimal("200.3800000000")

    binance.price = Decimal("199")
    candle(engine, entry_time + 4 * MINUTE, Decimal("199"), high=Decimal("205"), low=Decimal("199"))
    execution.synchronize(SYMBOL)
    closed = rows(engine, "SELECT * FROM paper_positions")[0]
    assert closed["status"] == "closed"
    assert closed["exit_reason"] == "break_even", "the floor sold it, not the -4.5% stop and not the line"
    # Without an order on Binance the bot sells at market, so the fill is this minute's price rather than the
    # floor itself. Live, the parked stop-limit at $200.38 is what fills - see the test above.
    assert closed["raw_exit_price"] == Decimal("199.0000000000")


def test_a_lot_opened_outside_an_uptrend_keeps_the_giveback_exit(database):
    world = build_world(database, uptrend=False)
    execution, binance, engine = world
    entry_time = open_a_lot(world)

    position = rows(engine, "SELECT * FROM paper_positions")[0]
    assert position["trend_exit_active"] is False, "no clean uptrend at the buy, so this is a Mode B lot"

    # 30% of the $10 peak gain gives back to 207; a minute through that level sells at once.
    binance.price = Decimal("205")
    candle(engine, entry_time + 4 * MINUTE, Decimal("205"), high=Decimal("210"), low=Decimal("205"))
    execution.synchronize(SYMBOL)
    closed = rows(engine, "SELECT status, exit_reason FROM paper_positions")[0]
    assert closed["status"] == "closed" and closed["exit_reason"] == "trailing_stop"


def test_the_trend_line_is_rebuilt_from_stored_candles_after_a_restart(database):
    """The EMA lives in engine state; if that is lost the service must warm it up again, not sell blindly."""
    world = build_world(database, uptrend=True)
    execution, binance, engine = world
    entry_time = open_a_lot(world)
    with engine.begin() as connection:
        state = connection.execute(text("SELECT value FROM engine_state WHERE key='live_execution'")).scalar_one()
        assert Decimal(state[SYMBOL]["ema"]) > 0
        state[SYMBOL].pop("ema")
        state[SYMBOL].pop("ema_at")
        connection.execute(text("UPDATE engine_state SET value=CAST(:v AS jsonb) WHERE key='live_execution'"),
                           {"v": json.dumps(state)})

    binance.price = Decimal("205")
    candle(engine, entry_time + 4 * MINUTE, Decimal("205"), high=Decimal("210"), low=Decimal("205"))
    execution.synchronize(SYMBOL)
    assert rows(engine, "SELECT status FROM paper_positions")[0]["status"] == "open"
    with engine.begin() as connection:
        state = connection.execute(text("SELECT value FROM engine_state WHERE key='live_execution'")).scalar_one()
    assert Decimal(state[SYMBOL]["ema"]) > 0, "the trend line must be warmed up again from stored candles"


# ------------------------------------------------------------------ Mode C, end to end

def quiet_then_break(engine, start, chart=120, bars=12):
    """Twelve flat 2-hour bars around $200, then one that closes well above them."""
    at = start
    for _ in range(bars):
        for _ in range(chart):
            candle(engine, at, Decimal("200"), high=Decimal("201"), low=Decimal("199"))
            at += MINUTE
    for minute in range(chart):                       # the breaking bar: closes at 210, far above the 201 top
        candle(engine, at, Decimal("210"), high=Decimal("211"), low=Decimal("205"))
        at += MINUTE
    return at


def test_a_consolidation_break_becomes_a_signal_and_then_a_lot(database):
    """The whole Mode C path: quiet bars, a break, the wait, the buy - with Mode C's own tighter stop."""
    from app.services.consolidation_service import ConsolidationService
    world = build_world(database, uptrend=False)
    execution, binance, engine = world
    strategy = load_strategies()[SYMBOL]
    service = ConsolidationService(engine, strategy)
    assert service.enabled

    # 12:00 UTC start keeps the whole run clear of the 06:00-12:00 blocked window
    start = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    after_break = quiet_then_break(engine, start)
    status = service.synchronize()
    assert status["breakouts_seen"] == 1
    signal = rows(engine, "SELECT * FROM signals WHERE strategy_id=:s", s=strategy["strategy_id"])[0]
    assert signal["status"] == "pending_confirmation"
    assert signal["details"]["kind"] == "consolidation"
    assert Decimal(signal["details"]["zone_top"]) == Decimal("201")

    # the wait: price holds above the zone top, so the break confirms
    confirm_at = after_break - MINUTE + 30 * MINUTE
    at = after_break
    while at <= confirm_at:
        candle(engine, at, Decimal("209"))
        at += MINUTE
    service.synchronize()
    signal = rows(engine, "SELECT * FROM signals")[0]
    assert signal["status"] == "confirmed"
    assert signal["entry_time"] == confirm_at + MINUTE

    # the account walks up to the entry minute and buys
    binance.price = Decimal("209")
    candle(engine, confirm_at + MINUTE, Decimal("209"))
    execution.synchronize(SYMBOL)
    position = rows(engine, "SELECT * FROM paper_positions")[0]
    assert position["entry_source"] == "breakout"
    # Mode C's own -3.5% stop (209 * 0.965, rounded down to the price tick), not the dip rule's -4.5%
    assert position["stop_price"] == Decimal("201.6700000000")
    assert position["stop_price"] > Decimal("209") * Decimal("0.955")


def test_a_break_that_falls_back_never_buys(database):
    from app.services.consolidation_service import ConsolidationService
    world = build_world(database, uptrend=False)
    execution, binance, engine = world
    strategy = load_strategies()[SYMBOL]
    service = ConsolidationService(engine, strategy)

    start = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    after_break = quiet_then_break(engine, start)
    service.synchronize()
    confirm_at = after_break - MINUTE + 30 * MINUTE
    at = after_break
    while at <= confirm_at:
        candle(engine, at, Decimal("198"))            # straight back inside the zone
        at += MINUTE
    service.synchronize()
    signal = rows(engine, "SELECT status, reason, entry_time FROM signals")[0]
    assert signal["status"] == "expired"
    assert signal["entry_time"] is None
    assert "fell back" in signal["reason"]

    candle(engine, confirm_at + MINUTE, Decimal("198"))
    execution.synchronize(SYMBOL)
    assert rows(engine, "SELECT * FROM paper_positions") == []


def test_mode_c_lots_exit_on_their_own_numbers(database):
    """A Mode C lot arms at +1.283% and gives back 22%, where a dip lot arms at +1.315% and gives back 30%."""
    from app.domain.paper_execution import ExecutionConfig

    config = ExecutionConfig.from_strategy(load_strategies()[SYMBOL])
    dip = config.for_source("signal")
    breakout = config.for_source("breakout")
    assert (dip.stop_pct, dip.trail_activation_pct, dip.trail_giveback_pct) == (Decimal("4.5"), Decimal("1.315"), Decimal("30.0"))
    assert (breakout.stop_pct, breakout.trail_activation_pct, breakout.trail_giveback_pct) == (Decimal("3.5"), Decimal("1.283"), Decimal("22.0"))
    # the trend exit is shared: a Mode C lot bought in an uptrend rides the line like any other
    assert breakout.trend_exit_ema_minutes == 960
