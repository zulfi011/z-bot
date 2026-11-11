"""The pyramid add-on: the pure rule, then end to end through the database and the execution service.

Proves the wiring: a lot that climbs a step gets another lot added to it, the add knows its parent, it carries its
own stop and always the trend ride, it stops at the maximum, it obeys the blocked hours, it can be
switched off, and it can be given lots of its own that the core cannot take (and vice versa).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.strategy import load_strategies, validate_strategy
from app.domain.pyramid import PyramidConfig, wants_add
from app.services.binance_client import BinanceClient
from app.services.binance_exchange import BinanceExchange
from app.services.live_execution_service import LiveExecutionService
from test_trend_exit_integration import FakeBinance, candle, database, rows  # noqa: F401  (shared fixture)

SYMBOL = "ETHUSDT"
MINUTE = timedelta(minutes=1)
T0 = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)      # outside the 06-12 blocked window
RULE = PyramidConfig(step_pct=Decimal("1"), maximum_adds=3, blocked_entry_hours=(6, 12))
D = Decimal


# ------------------------------------------------------------------ the rule
def test_each_level_needs_another_step():
    assert not wants_add(RULE, D("100"), 0, D("100.9"), D("99"), T0), "under +1%"
    assert wants_add(RULE, D("100"), 0, D("101"), D("99"), T0), "exactly +1% counts"
    assert not wants_add(RULE, D("100"), 1, D("101.5"), D("99"), T0), "the second add needs +2%"
    assert wants_add(RULE, D("100"), 1, D("102"), D("99"), T0)
    assert wants_add(RULE, D("100"), 2, D("103"), D("99"), T0)


def test_it_stops_at_the_maximum_and_never_adds_below_the_line():
    assert not wants_add(RULE, D("100"), 3, D("110"), D("99"), T0), "three adds is the limit"
    assert not wants_add(RULE, D("100"), 0, D("101"), D("101"), T0), "a close level with the line is not above it"
    assert not wants_add(RULE, D("100"), 0, D("101"), None, T0), "no line yet, no adds"


def test_the_blocked_hours_are_obeyed():
    assert not wants_add(RULE, D("100"), 0, D("105"), D("99"), T0.replace(hour=7))
    assert wants_add(RULE, D("100"), 0, D("105"), D("99"), T0.replace(hour=12))


def test_only_sol_has_an_add_on():
    """SOL is the one coin with a pyramid. ETH's was removed: it won barely half its adds and cost the whole
    strategy eight points of win rate, so the strategy file no longer carries the rule at all."""
    strategies = load_strategies()
    assert PyramidConfig.from_strategy(strategies["SOLUSDT"]) == PyramidConfig(
        step_pct=Decimal("0.5"), maximum_adds=2, add_exit="with_parent", blocked_entry_hours=(6, 12))
    assert PyramidConfig.from_strategy(strategies["SOLUSDT"]).follows_parent is True
    assert all(PyramidConfig.from_strategy(s) is None
               for symbol, s in strategies.items() if symbol != "SOLUSDT")


def test_an_add_exit_has_to_be_one_of_the_two_kinds():
    strategy = copy.deepcopy(load_strategies()["SOLUSDT"])
    strategy["entry"]["pyramid_add"]["add_exit"] = "whenever"
    with pytest.raises(RuntimeError, match="with_parent"):
        validate_strategy(strategy)


# ------------------------------------------------------------------ end to end
# ETH's add-on as it was before it was removed from eth_strategy.json: the engine paths it exercises (own exit,
# exit with the parent, sharing lots) are still live code, used by SOL.
ETH_STYLE_ADD = {"step_pct": 1.0, "maximum_adds": 3, "add_exit": "own"}


def build(database, *, lots=3, pyramid=True, start=T0, add_exit=None, live=True):
    strategy = copy.deepcopy(load_strategies()[SYMBOL])
    strategy["entry"]["pyramid_add"] = dict(ETH_STYLE_ADD)
    if add_exit:
        strategy["entry"]["pyramid_add"]["add_exit"] = add_exit
    strategy = validate_strategy(strategy)
    binance = FakeBinance()
    client = BinanceClient("key", "secret")
    client._request = binance.request  # type: ignore[method-assign]
    execution = LiveExecutionService(database, {SYMBOL: strategy}, BinanceExchange(client, live=live))
    with database.begin() as connection:
        for table in ("trades", "orders", "positions", "signals", "touch_episodes",
                      "candles_1m", "exchange_events", "monitoring_alerts", "account_snapshots",
                      "system_events", "control_requests", "engine_state", "daily_averages"):
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(
            text("""INSERT INTO coin_allocations (symbol, pullback_enabled, pyramid_enabled, trading_enabled, updated_at)
                    VALUES (:s, false, :pyramid, true, now())
                    ON CONFLICT (symbol) DO UPDATE SET pullback_enabled=false,
                        pyramid_enabled=:pyramid, trading_enabled=true"""),
            {"s": SYMBOL, "pyramid": pyramid})
        connection.execute(
            text("""INSERT INTO engine_state (key, value) VALUES ('account_settings', CAST(:v AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value=CAST(:v AS jsonb)"""),
            {"v": json.dumps({"trading_mode": "live", "daily_loss_limit_usd": "0", "maximum_open_value_usd": "0",
                              "pot_lots": lots, "pot_lot_size_usd": "100"})})
        connection.execute(
            text("""INSERT INTO daily_averages (symbol, effective_at, completed_through, average_7d, average_15d,
                                                average_30d, signal_average_days, signal_average)
                    VALUES (:s, :at, :day, 210, 205, 200, 7, 210)"""),
            {"s": SYMBOL, "at": start.replace(hour=0, minute=0), "day": start.date() - timedelta(days=1)})
    return execution, binance, strategy


def dip_signal(engine, strategy_id, at, name="dip1") -> None:
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO touch_episodes (episode_id, strategy_id, symbol, touch_time,
                                       average_value, status) VALUES (:n, :id, :s, :t, 200, 'confirmed')"""),
                           {"n": name, "id": strategy_id, "s": SYMBOL, "t": at})
        connection.execute(text("""INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, entry_time,
                                       status) VALUES (:n, :n, :id, :t, :t, 'confirmed')"""),
                           {"n": name, "id": strategy_id, "t": at})


def open_parent(world, database, start=T0):
    """Buy one $100 lot at $200 through the ordinary dip signal."""
    execution, binance, strategy = world
    candle(database, start, Decimal("200"))
    execution.synchronize(SYMBOL)
    entry = start + MINUTE
    candle(database, entry, Decimal("200"))
    dip_signal(database, strategy["strategy_id"], entry)
    execution.synchronize(SYMBOL)
    return entry


def climb(execution, database, binance, start, prices):
    for index, price in enumerate(prices, start=1):
        binance.price = Decimal(str(price))
        candle(database, start + index * MINUTE, Decimal(str(price)))
    execution.synchronize(SYMBOL)


def test_a_climbing_lot_gets_lots_added_to_it(database):
    world = build(database, lots=4)
    execution, binance, _ = world
    entry = open_parent(world, database)
    parent = rows(database, "SELECT position_id, entry_fill_price FROM positions")[0]

    climb(execution, database, binance, entry, [201, 202])        # +1% = 202
    adds = rows(database, "SELECT * FROM positions WHERE entry_source='pyramid' ORDER BY entry_time")
    assert len(adds) == 1, "one step, one add"
    assert adds[0]["parent_position_id"] == parent["position_id"]
    assert adds[0]["trend_exit_active"] is True, "an add is always held against the line"
    expected_stop = adds[0]["entry_fill_price"] * Decimal("0.955")
    assert abs(adds[0]["stop_price"] - expected_stop) < Decimal("0.02"), "its own -4.5% stop from its own fill"
    assert adds[0]["stop_price"] > Decimal("192"), "and well above the parent's stop, which sits at 191"

    climb(execution, database, binance, entry + 2 * MINUTE, [203, 204])   # +2% = 204
    assert len(rows(database, "SELECT * FROM positions WHERE entry_source='pyramid'")) == 2
    assert rows(database, "SELECT count(*) AS n FROM positions")[0]["n"] == 3


def test_it_never_adds_more_than_the_maximum_and_never_to_an_add(database):
    world = build(database, lots=9)
    execution, binance, _ = world
    entry = open_parent(world, database)
    climb(execution, database, binance, entry, [202, 204, 206, 208, 210, 212])
    adds = rows(database, "SELECT parent_position_id FROM positions WHERE entry_source='pyramid'")
    assert len(adds) == 3, "three is the maximum"
    assert len({row["parent_position_id"] for row in adds}) == 1, "adds are never themselves parents"


def test_switched_off_it_adds_nothing(database):
    world = build(database, lots=4, pyramid=False)
    execution, binance, _ = world
    entry = open_parent(world, database)
    climb(execution, database, binance, entry, [202, 204])
    assert rows(database, "SELECT * FROM positions WHERE entry_source='pyramid'") == []


def test_it_shares_the_coins_lots_and_stops_when_they_run_out(database):
    """There are no reserved lots: an add takes a free lot, and when none is free nothing is added."""
    world = build(database, lots=1)          # the parent takes the only lot
    execution, binance, _ = world
    entry = open_parent(world, database)
    climb(execution, database, binance, entry, [202, 204])
    assert rows(database, "SELECT * FROM positions WHERE entry_source='pyramid'") == [], \
        "no free lot, so nothing is added"


def test_with_more_lots_the_adds_fill_the_free_ones(database):
    world = build(database, lots=3)
    execution, binance, _ = world
    entry = open_parent(world, database)     # one of the three lots is taken by the parent
    climb(execution, database, binance, entry, [202, 204, 206])
    adds = rows(database, "SELECT * FROM positions WHERE entry_source='pyramid'")
    assert len(adds) == 2, "the two free lots are filled by adds, then the coin is full"
    assert rows(database, "SELECT count(*) AS n FROM positions")[0]["n"] == 3


def test_the_blocked_hours_stop_adds_live(database):
    start = datetime(2026, 9, 1, 5, 58, tzinfo=timezone.utc)      # the parent opens at 05:59, the climb is inside 06-12
    world = build(database, lots=4, start=start)
    execution, binance, _ = world
    entry = open_parent(world, database, start)
    climb(execution, database, binance, entry, [202, 204, 206, 208, 210])
    assert rows(database, "SELECT * FROM positions WHERE entry_source='pyramid'") == []


# ------------------------------------------------- adds that leave with their parent (SOL's setting)
def test_an_add_that_follows_its_parent_carries_the_parents_stop(database):
    world = build(database, lots=4, add_exit="with_parent")
    execution, binance, _ = world
    entry = open_parent(world, database)
    parent = rows(database, "SELECT position_id, stop_price FROM positions")[0]

    climb(execution, database, binance, entry, [201, 202])
    add = rows(database, "SELECT * FROM positions WHERE entry_source='pyramid'")[0]
    assert add["parent_position_id"] == parent["position_id"]
    assert add["stop_price"] == parent["stop_price"], "it parks the parent's level, not one off its own fill"
    assert add["trend_exit_active"] is False, "it has no exit rules of its own"


def test_an_add_is_sold_in_the_same_minute_its_parent_is(database):
    # live=False: with no order parked on Binance the bot does the selling itself, which is what this test
    # watches. Live, the parent's own stop fills on the exchange and the add follows on the next pass.
    world = build(database, lots=4, add_exit="with_parent", live=False)
    execution, binance, _ = world
    entry = open_parent(world, database)
    climb(execution, database, binance, entry, [201, 202, 203])      # one add at +1%, and the parent's trail arms
    assert len(rows(database, "SELECT * FROM positions WHERE status='open'")) == 2

    # The parent comes back to its entry, so its break-even floor sells it - and the add goes in the same pass.
    binance.price = Decimal("195")
    candle(database, entry + 4 * MINUTE, Decimal("195"), high=Decimal("203"), low=Decimal("195"))
    execution.synchronize(SYMBOL)
    closed = rows(database, "SELECT * FROM positions WHERE status='closed' ORDER BY entry_time")
    assert len(closed) == 2, "the parent and its add both leave"
    assert closed[0]["exit_reason"] == "break_even"
    assert closed[1]["exit_reason"] == "parent_exit"
    assert abs(closed[1]["exit_time"] - closed[0]["exit_time"]) < timedelta(seconds=1), "the same pass"
    assert closed[1]["raw_exit_price"] == closed[0]["raw_exit_price"]
    assert binance.coin == Decimal("0") and binance.locked == Decimal("0"), "no coin and no parked stop left behind"


def test_eth_style_adds_keep_running_after_their_parent_leaves(database):
    world = build(database, lots=4, live=False)   # add_exit "own", straight from the ETH strategy
    execution, binance, _ = world
    entry = open_parent(world, database)
    climb(execution, database, binance, entry, [201, 202, 203])      # one add at +1%, and the parent's trail arms

    # A dip that takes the parent's line but stays above the add's own stop (202 fill, stop near 193). The add's
    # own trail has not armed yet, so the trend ride cannot sell it and it keeps running.
    for index, price in enumerate([Decimal("195"), Decimal("195")], start=4):
        binance.price = price
        candle(database, entry + index * MINUTE, price, high=Decimal("202"), low=price)
        execution.synchronize(SYMBOL)
    open_now = rows(database, "SELECT entry_source FROM positions WHERE status='open'")
    assert [row["entry_source"] for row in open_now] == ["pyramid"], "the add outlives the parent"
