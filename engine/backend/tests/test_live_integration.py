"""A whole lot's life, end to end: buy, parked stop, trailing, sell — real SQL, real order building, fake Binance.

This runs the actual LiveExecutionService against a throwaway PostgreSQL database created by the real migrations,
with Binance replaced at the HTTP layer only. So the signing, the exchange filters, every INSERT and UPDATE, the
cursor bookkeeping and the exit rules are all the production code paths. It is skipped when no database is
reachable (INTEGRATION_DATABASE_URL, or the local compose database).
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.strategy import load_strategies
from app.services.binance_client import BinanceClient, BinanceError
from app.services.binance_exchange import BinanceExchange
from app.services.live_execution_service import LiveExecutionService

BASE_URL = os.environ.get("INTEGRATION_DATABASE_URL",
                          "postgresql+psycopg://paperbot:paperbot_local@db:5432/papertrading")
SYMBOL = "SOLUSDT"
MINUTE = timedelta(minutes=1)
START = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)  # 13:00 UTC: outside the 06-12 blocked window

EXCHANGE_INFO = {"symbols": [{"symbol": SYMBOL, "orderTypes": ["LIMIT", "MARKET", "STOP_LOSS_LIMIT"], "filters": [
    {"filterType": "LOT_SIZE", "stepSize": "0.01000000", "minQty": "0.01000000"},
    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
    {"filterType": "NOTIONAL", "minNotional": "5.00000000"}]}]}


class FakeBinance:
    """Binance's HTTP answers. Orders fill at the price the test sets, and fees are taken in BNB."""

    def __init__(self) -> None:
        self.price = Decimal("200")
        self.usdt = Decimal("1000")
        self.coin = Decimal("0")
        self.orders: dict[str, dict] = {}
        self.sent: list[tuple[str, dict]] = []
        self._next_id = 1000

    # -- helpers the test drives
    def fill_stop(self, order_id: str, price: Decimal) -> None:
        order = self.orders[str(order_id)]
        quantity = Decimal(order["origQty"])
        order.update(status="FILLED", executedQty=order["origQty"],
                     cummulativeQuoteQty=str(quantity * price))
        self.locked -= quantity
        self.usdt += quantity * price

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
                {"asset": "SOL", "free": str(self.coin), "locked": str(getattr(self, "locked", Decimal("0")))},
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
            if order["type"] == "STOP_LOSS_LIMIT":
                self.locked -= Decimal(order["origQty"])
                self.coin += Decimal(order["origQty"])
            self.sent.append(("cancel", params))
            return order
        if path == "/api/v3/myTrades":
            quantity = Decimal(self.orders[str(params["orderId"])]["executedQty"])
            return [{"commission": str((quantity * self.price / Decimal("600")) * Decimal("0.00075")),
                     "commissionAsset": "BNB"}]
        if path == "/api/v3/openOrders":
            return [order for order in self.orders.values() if order["status"] == "NEW"]
        raise AssertionError(f"unexpected Binance call: {method} {path}")

    def _place(self, params: dict) -> dict:
        self._next_id += 1
        order_id = self._next_id
        order = {"orderId": order_id, "clientOrderId": params.get("newClientOrderId"), "symbol": params["symbol"],
                 "side": params["side"], "type": params["type"], "status": "NEW", "executedQty": "0",
                 "cummulativeQuoteQty": "0", "origQty": params.get("quantity", "0")}
        self.sent.append((params["type"] + ":" + params["side"], params))
        if params["type"] == "STOP_LOSS_LIMIT":
            order["origQty"] = params["quantity"]
            self.locked = getattr(self, "locked", Decimal("0")) + Decimal(params["quantity"])
            self.coin -= Decimal(params["quantity"])
        if params["type"] == "MARKET" and params["side"] == "BUY":
            spend = Decimal(params["quoteOrderQty"])
            quantity = (spend / self.price).quantize(Decimal("0.01"))
            fee = (spend / Decimal("600")) * Decimal("0.00075")  # paid in BNB, so the coin arrives whole
            self.usdt -= spend
            self.coin += quantity
            order.update(status="FILLED", executedQty=str(quantity), cummulativeQuoteQty=str(spend),
                         origQty=str(quantity),
                         fills=[{"price": str(self.price), "qty": str(quantity), "commission": str(fee),
                                 "commissionAsset": "BNB"}])
        elif params["type"] == "MARKET" and params["side"] == "SELL":
            quantity = Decimal(params["quantity"])
            received = quantity * self.price
            fee = (received / Decimal("600")) * Decimal("0.00075")
            self.usdt += received
            self.coin -= quantity
            order.update(status="FILLED", executedQty=str(quantity), cummulativeQuoteQty=str(received),
                         fills=[{"price": str(self.price), "qty": str(quantity), "commission": str(fee),
                                 "commissionAsset": "BNB"}])
        self.orders[str(order_id)] = order
        return order


@pytest.fixture(scope="module")
def database():
    """A throwaway database built by the real migrations, dropped afterwards."""
    admin_url = BASE_URL.rsplit("/", 1)[0] + "/postgres"
    name = f"zbot_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as error:  # no database around: this suite is optional
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


@pytest.fixture
def world(database):
    """An account with one SOL lot allowed, live mode, and a fake Binance behind the real client."""
    binance = FakeBinance()
    client = BinanceClient("key", "secret")
    client._request = binance.request  # type: ignore[method-assign]
    exchange = BinanceExchange(client, live=True)
    strategies = {SYMBOL: load_strategies()[SYMBOL]}
    execution = LiveExecutionService(database, strategies, exchange)
    with database.begin() as connection:
        connection.execute(text("DELETE FROM paper_trades"))
        connection.execute(text("DELETE FROM paper_orders"))
        connection.execute(text("DELETE FROM paper_positions"))
        connection.execute(text("DELETE FROM signals"))
        connection.execute(text("DELETE FROM touch_episodes"))
        connection.execute(text("DELETE FROM candles_1m"))
        connection.execute(text("DELETE FROM exchange_events"))
        connection.execute(text("DELETE FROM monitoring_alerts"))
        connection.execute(text("DELETE FROM account_snapshots"))
        connection.execute(text("DELETE FROM system_events"))
        connection.execute(text("DELETE FROM control_requests"))
        connection.execute(text("DELETE FROM engine_state"))
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
    return execution, binance, database


def candle(engine, at: datetime, price: Decimal, high: Decimal | None = None, low: Decimal | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO candles_1m (symbol, open_time, open, high, low, close, volume, source)
                    VALUES (:s, :t, :o, :h, :l, :c, 1, 'test') ON CONFLICT (symbol, open_time) DO NOTHING"""),
            {"s": SYMBOL, "t": at, "o": price, "h": high or price, "l": low or price, "c": price})


def confirmed_signal(engine, at: datetime, strategy_id: str, name: str = "s1") -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO touch_episodes (episode_id, strategy_id, symbol, touch_time, average_value, status)
                    VALUES (:id, :strategy, :s, :t, 200, 'confirmed')"""),
            {"id": f"episode:{name}", "strategy": strategy_id, "s": SYMBOL, "t": at})
        connection.execute(
            text("""INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, entry_time, status)
                    VALUES (:id, :episode, :strategy, :t, :t, 'confirmed')"""),
            {"id": name, "episode": f"episode:{name}", "strategy": strategy_id, "t": at})


def rows(engine, sql: str, **params) -> list[dict]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(sql), params).mappings().all()]


# ------------------------------------------------------------------ the tests
def test_a_lot_is_bought_protected_trailed_and_sold(world):
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id

    # The bot starts at the newest candle, so lay down one minute first and let it take its cursor.
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    assert rows(engine, "SELECT * FROM paper_positions") == []

    # A confirmed signal on the next minute: this is where the money moves.
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)

    position = rows(engine, "SELECT * FROM paper_positions")[0]
    assert position["status"] == "open"
    assert position["allocation_usd"] == Decimal("100.00")
    assert position["quantity"] == Decimal("0.500000000000")           # $100 at $200, fee paid in BNB
    assert position["entry_fee_asset"] == "BNB"
    assert position["entry_order_id"] and position["stop_order_id"]
    assert position["stop_price"] == Decimal("196.0000000000")          # SOL's stop is 2% under the fill

    # The stop really is parked on Binance, as a STOP_LOSS_LIMIT to sell everything we hold.
    parked = binance.orders[position["stop_order_id"]]
    assert parked["type"] == "STOP_LOSS_LIMIT" and parked["side"] == "SELL" and parked["status"] == "NEW"
    assert Decimal(parked["origQty"]) == Decimal("0.5")

    # Price climbs past SOL's +1.251% activation, so the trailing stop arms.
    climb = [Decimal("201"), Decimal("202"), Decimal("203"), Decimal("204")]
    for index, price in enumerate(climb, start=1):
        binance.price = price
        candle(engine, entry_time + index * MINUTE, price)
    execution.synchronize(SYMBOL)
    armed = rows(engine, "SELECT trailing_active, peak_price FROM paper_positions")[0]
    assert armed["trailing_active"] is True
    assert armed["peak_price"] == Decimal("204.0000000000")

    # It gives back 12% of the peak profit: 204 - 0.12 * (204 - 200) = 203.52. A candle through that sells.
    binance.price = Decimal("203")
    candle(engine, entry_time + 5 * MINUTE, Decimal("203"), high=Decimal("204"), low=Decimal("203"))
    execution.synchronize(SYMBOL)

    closed = rows(engine, "SELECT * FROM paper_positions")[0]
    assert closed["status"] == "closed" and closed["exit_reason"] == "trailing_stop"
    assert closed["quantity_sold"] == Decimal("0.500000000000")
    assert closed["exit_order_id"]
    assert binance.orders[position["stop_order_id"]]["status"] == "CANCELED"   # the parked stop was pulled first
    assert binance.coin == Decimal("0")                                        # nothing of ours is left on Binance

    trade = rows(engine, "SELECT * FROM paper_trades")[0]
    assert trade["symbol"] == SYMBOL and trade["exit_reason"] == "trailing_stop"
    assert trade["net_pnl_usd"] > 0
    # Both fees were taken in BNB; with no BNBUSDT candle stored they are valued from Binance's ticker.
    assert trade["bnb_fees_usd"] > 0
    assert trade["entry_fee_usd"] > 0 and trade["exit_fee_usd"] > 0
    orders = rows(engine, "SELECT side, status, exchange_order_id FROM paper_orders ORDER BY side")
    assert [(o["side"], o["status"]) for o in orders] == [("buy", "filled"), ("sell", "filled")]
    assert all(o["exchange_order_id"] for o in orders)

    events = rows(engine, "SELECT action, ok FROM exchange_events ORDER BY id")
    assert [event["action"] for event in events] == ["market_buy", "protective_stop", "cancel_stop", "market_sell"]
    assert all(event["ok"] for event in events)


def test_a_crash_is_sold_by_binances_own_stop_and_recorded(world):
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)
    position = rows(engine, "SELECT * FROM paper_positions")[0]

    # Binance fills the parked stop while the app is not looking, below the stop price.
    binance.price = Decimal("195")
    binance.fill_stop(position["stop_order_id"], Decimal("195.5"))
    candle(engine, entry_time + MINUTE, Decimal("195"), high=Decimal("200"), low=Decimal("194"))
    execution.synchronize(SYMBOL)

    closed = rows(engine, "SELECT * FROM paper_positions")[0]
    assert closed["status"] == "closed" and closed["exit_reason"] == "protective_stop"
    assert closed["exit_cash_usd"] == Decimal("97.75000000")           # 0.5 at 195.50
    trade = rows(engine, "SELECT * FROM paper_trades")[0]
    assert trade["net_pnl_usd"] < 0 and trade["exit_fee_usd"] > 0      # the real commission came from myTrades
    # No second sell was sent: Binance had already done it.
    assert [kind for kind, _ in binance.sent if kind.startswith("MARKET:SELL")] == []


def test_shadow_mode_records_the_same_lot_without_touching_binance(world):
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    with engine.begin() as connection:
        connection.execute(text("""UPDATE engine_state SET value = jsonb_set(value, '{trading_mode}', '"shadow"')
                                   WHERE key='account_settings'"""))
    execution.exchange.live = False
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)

    position = rows(engine, "SELECT * FROM paper_positions")[0]
    assert position["status"] == "open" and position["quantity"] == Decimal("0.500000000000")
    assert position["entry_order_id"] is None                      # nothing was sent, so there is no Binance id
    assert rows(engine, "SELECT status FROM paper_orders")[0]["status"] == "shadow"
    assert binance.sent == [] and binance.usdt == Decimal("1000")   # the wallet is untouched
    assert [event["action"] for event in rows(engine, "SELECT action FROM exchange_events ORDER BY id")] == \
        ["market_buy", "protective_stop"]


def test_another_coins_open_lot_fills_the_shared_pot(world):
    """The pot has one lot and ETH is holding it, so a SOL signal is skipped: lots belong to the pot, not the coin."""
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO paper_positions (position_id, symbol, entry_source, lot_number, status,
                                       entry_time, raw_entry_price, entry_fill_price, quantity, allocation_usd,
                                       entry_fee_usd, entry_fee_asset)
                                   VALUES ('position:eth1', 'ETHUSDT', 'signal', 1, 'open', now(), 3000, 3000,
                                       0.033, 100, 0.07, 'BNB')"""))
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)
    assert rows(engine, "SELECT symbol FROM paper_positions") == [{"symbol": "ETHUSDT"}]
    signal = rows(engine, "SELECT status, reason FROM signals")[0]
    assert signal["status"] == "ignored_not_allowed" and "All 1 shared lots are open" in signal["reason"]
    assert binance.sent == []


def test_nothing_is_bought_without_an_allocation_or_when_paused(world):
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    with engine.begin() as connection:
        connection.execute(text("UPDATE coin_allocations SET trading_enabled=false WHERE symbol=:s"), {"s": SYMBOL})
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)
    assert rows(engine, "SELECT * FROM paper_positions") == []
    signal = rows(engine, "SELECT status, reason FROM signals")[0]
    assert signal["status"] == "ignored_not_allowed" and "switched off" in signal["reason"]
    assert binance.sent == []


def test_a_restart_in_the_middle_of_a_buy_never_buys_twice(world):
    """Binance fills the buy, then the app dies before the ledger commits. The restart must adopt that order."""
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)

    real_place_stop = execution._place_stop

    def crash(*args, **kwargs):
        raise RuntimeError("power cut right after the buy filled")

    execution._place_stop = crash
    with pytest.raises(RuntimeError):
        execution.synchronize(SYMBOL)
    # The money really moved on Binance, but the ledger rolled back: nothing is recorded yet.
    assert binance.coin == Decimal("0.5")
    assert rows(engine, "SELECT * FROM paper_positions") == []

    execution._place_stop = real_place_stop        # the app comes back
    execution.synchronize(SYMBOL)

    buys = [params for kind, params in binance.sent if kind == "MARKET:BUY"]
    assert len(buys) == 1                                           # one buy on Binance, not two
    assert binance.usdt == Decimal("900") and binance.locked == Decimal("0.5")   # 0.5 SOL, held by its stop
    position = rows(engine, "SELECT * FROM paper_positions")[0]
    assert position["status"] == "open" and position["quantity"] == Decimal("0.500000000000")
    assert position["entry_order_id"] == str(next(o for o in binance.orders.values() if o["side"] == "BUY")["orderId"])
    assert position["stop_order_id"]                                # and it is protected after all
    recovered = rows(engine, "SELECT action, response FROM exchange_events WHERE action='market_buy'")
    assert len(recovered) == 1


def test_the_wallet_value_is_what_binance_holds_not_usdt_plus_the_ledger(world):
    """Right after a buy, and with the coin locked in its stop order, the wallet is still $1,000 - not $1,100."""
    execution, binance, engine = world
    strategy_id = execution.coins[SYMBOL].strategy_id
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO candles_1m (symbol, open_time, open, high, low, close, volume, source)
                    VALUES ('BNBUSDT', :t, 600, 600, 600, 600, 1, 'test')"""), {"t": START})
    candle(engine, START, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry_time = START + MINUTE
    candle(engine, entry_time, Decimal("200"))
    confirmed_signal(engine, entry_time, strategy_id)
    execution.synchronize(SYMBOL)

    snapshot = rows(engine, "SELECT * FROM account_snapshots ORDER BY timestamp DESC LIMIT 1")[0]
    assert snapshot["open_positions"] == 1
    # $900 USDT + 0.5 SOL at $200 + 0.5 BNB at $600 = $1,300; the buy's own fee is a few cents of BNB.
    assert snapshot["usdt_free"] == Decimal("900.00000000")
    assert snapshot["wallet_value_usd"] == Decimal("1300.00000000")


def test_a_fresh_start_shows_one_calm_notice_instead_of_red_price_alarms(world):
    from app.services.monitoring_service import MonitoringService
    execution, _, engine = world
    strategies = {SYMBOL: load_strategies()[SYMBOL]}
    just_started = MonitoringService(engine, strategies, 180, started_at=datetime.now(timezone.utc))
    just_started.synchronize()                     # no fresh candles at all: exactly what a restart looks like
    active = {row["alert_key"]: row["severity"] for row in
              rows(engine, "SELECT alert_key, severity FROM monitoring_alerts WHERE status='active'")}
    assert active.get("starting_up") == "warning"
    assert not any(key.startswith(("market_data_stale", "market_data_gap")) or key == "execution_lag" for key in active)

    long_running = MonitoringService(engine, strategies, 180, started_at=datetime.now(timezone.utc) - timedelta(hours=1))
    long_running.synchronize()                     # an hour later the same silence is a real outage
    active = {row["alert_key"] for row in rows(engine, "SELECT alert_key FROM monitoring_alerts WHERE status='active'")}
    assert f"market_data_stale:{SYMBOL}" in active
    assert "starting_up" not in active             # and the start-up notice cleared itself


def test_every_alert_clears_itself_when_its_problem_is_gone(world):
    """'Trading is not live' used to stay on screen forever after going live."""
    from app.services.monitoring_service import MonitoringService
    execution, _, engine = world
    strategies = {SYMBOL: load_strategies()[SYMBOL]}
    monitor = MonitoringService(engine, strategies, 180)
    with engine.begin() as connection:
        connection.execute(text("""UPDATE engine_state SET value = jsonb_set(value, '{trading_mode}', '"shadow"')
                                   WHERE key='account_settings'"""))
    monitor.synchronize()
    assert rows(engine, "SELECT status FROM monitoring_alerts WHERE alert_key='not_live'")[0]["status"] == "active"
    with engine.begin() as connection:
        connection.execute(text("""UPDATE engine_state SET value = jsonb_set(value, '{trading_mode}', '"live"')
                                   WHERE key='account_settings'"""))
    monitor.synchronize()
    assert rows(engine, "SELECT status FROM monitoring_alerts WHERE alert_key='not_live'")[0]["status"] == "resolved"


def test_removing_link_refuses_while_a_link_lot_is_open(world):
    """Migration 0015 must never strand an open LINK lot that the bot would stop managing."""
    import importlib.util
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    folder = next(p for p in (Path("/src/migrations/versions"), Path(__file__).resolve().parents[1] / "migrations/versions")
                  if p.exists())
    spec = importlib.util.spec_from_file_location("remove_link", folder / "0015_remove_link.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def run():
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    _, _, engine = world
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO coin_allocations (symbol, updated_at)
                                   VALUES ('LINKUSDT', now())"""))
        connection.execute(text("""INSERT INTO paper_positions (position_id, symbol, entry_source, lot_number, status,
                                       entry_time, raw_entry_price, entry_fill_price, quantity, allocation_usd,
                                       entry_fee_usd, entry_fee_asset)
                                   VALUES ('position:link1', 'LINKUSDT', 'manual', 1, 'open', now(), 11, 11, 9, 100,
                                       0.07, 'BNB')"""))
    with pytest.raises(RuntimeError, match="LINK still has 1 open lot"):
        run()
    assert rows(engine, "SELECT symbol FROM coin_allocations WHERE symbol='LINKUSDT'")      # nothing removed

    with engine.begin() as connection:
        connection.execute(text("UPDATE paper_positions SET status='closed' WHERE position_id='position:link1'"))
    run()
    assert rows(engine, "SELECT symbol FROM coin_allocations WHERE symbol='LINKUSDT'") == []  # its share is back


def test_a_dropped_coin_cannot_hold_the_behind_alert_open(world):
    """LINK was removed from the strategy list but its cursor stayed in the engine state, two days stale.

    The lag check compared the newest candle against the OLDEST cursor of anything in that state, so the dead
    coin made the account look 2,587 minutes behind for ever. "The bot is behind" is critical and never cleared,
    so the only way to get rid of it was to dismiss it by hand — every single time the page loaded.
    """
    from app.services.monitoring_service import MonitoringService
    execution, _, engine = world
    strategies = {SYMBOL: load_strategies()[SYMBOL]}
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    candle(engine, now - MINUTE, Decimal("200"))
    candle(engine, now, Decimal("200"))
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO engine_state (key, value) VALUES ('live_execution', CAST(:v AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value=CAST(:v AS jsonb)"""),
            {"v": json.dumps({
                SYMBOL: {"last_open_time": now.isoformat()},                       # up to date
                "LINKUSDT": {"last_open_time": (now - timedelta(days=2)).isoformat()},  # no longer traded
            })})
    MonitoringService(engine, strategies, 180).synchronize()
    active = {row["alert_key"] for row in rows(engine, "SELECT alert_key FROM monitoring_alerts WHERE status='active'")}
    assert "execution_lag" not in active, "a coin the bot no longer trades must not make it look behind"


def set_cursor(engine, at):
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO engine_state (key, value) VALUES ('live_execution', CAST(:v AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value=CAST(:v AS jsonb)"""),
            {"v": json.dumps({SYMBOL: {"last_open_time": at.isoformat()}})})


def test_a_brief_wobble_never_raises_the_behind_alarm(world):
    """Five price feeds rarely deliver the same minute together, so the account is often a minute or two behind.

    That used to raise a critical red banner at once and clear it a minute later. It kept coming back, so it
    read as permanent and had to be dismissed by hand each time.
    """
    from app.services.monitoring_service import MonitoringService
    execution, _, engine = world
    strategies = {SYMBOL: load_strategies()[SYMBOL]}
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for minute in range(4):
        candle(engine, now - (3 - minute) * MINUTE, Decimal("200"))
    set_cursor(engine, now - 2 * MINUTE)                       # two minutes behind, just now
    MonitoringService(engine, strategies, 180).synchronize()
    assert not rows(engine, "SELECT 1 FROM monitoring_alerts WHERE alert_key='execution_lag' AND status='active'")

    set_cursor(engine, now)                                    # caught up again a moment later
    MonitoringService(engine, strategies, 180).synchronize()
    assert not rows(engine, "SELECT 1 FROM monitoring_alerts WHERE alert_key='execution_lag' AND status='active'")


def test_a_lag_that_lasts_is_reported_and_then_clears_itself(world):
    from app.services.monitoring_service import MonitoringService
    execution, _, engine = world
    strategies = {SYMBOL: load_strategies()[SYMBOL]}
    monitor = MonitoringService(engine, strategies, 180)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for minute in range(11):
        candle(engine, now - (10 - minute) * MINUTE, Decimal("200"))
    set_cursor(engine, now - 10 * MINUTE)
    # the account has been stuck since well before the grace window: this is a real stall, not a wobble
    with engine.begin() as connection:
        connection.execute(
            text("""INSERT INTO engine_state (key, value) VALUES ('monitoring', CAST(:v AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value=CAST(:v AS jsonb)"""),
            {"v": json.dumps({"behind_since": (now - 10 * MINUTE).isoformat()})})
    monitor.synchronize()
    alert = rows(engine, "SELECT status, message FROM monitoring_alerts WHERE alert_key='execution_lag'")[0]
    assert alert["status"] == "active"
    assert "10 minutes" in alert["message"]

    set_cursor(engine, now)                                    # caught up: nobody should have to dismiss anything
    monitor.synchronize()
    assert rows(engine, "SELECT status FROM monitoring_alerts WHERE alert_key='execution_lag'")[0]["status"] == "resolved"


def test_bnb_warnings_only_once_a_binance_account_is_attached(world, monkeypatch):
    """Someone trying shadow mode without Binance must not be told to buy BNB."""
    from app.core import credentials
    from app.services.monitoring_service import MonitoringService
    execution, _, engine = world
    execution._write_snapshot()
    with engine.begin() as connection:
        connection.execute(text("UPDATE account_snapshots SET bnb_free = 0, bnb_value_usd = 0"))
    monitor = MonitoringService(engine, {SYMBOL: load_strategies()[SYMBOL]}, 180)

    def active():
        return {row["alert_key"] for row in rows(engine, "SELECT alert_key FROM monitoring_alerts WHERE status='active'")}

    monkeypatch.setattr(credentials, "attached", lambda: False)
    monitor.synchronize()
    assert not {"bnb_empty", "bnb_low", "bnb_price_stale"} & active()
    monkeypatch.setattr(credentials, "attached", lambda: True)
    monitor.synchronize()
    assert "bnb_empty" in active()
