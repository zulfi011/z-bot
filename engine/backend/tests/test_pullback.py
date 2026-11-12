"""The pullback entry: the pure rule, then end to end through the database and the execution service.

The domain tests pin the rule to the research definition. The integration tests prove the wiring: a reclaim in an
uptrend becomes a confirmed signal and buys a lot from the coin's one set of lots, shared with the dip and the quiet-band breakout
first come first served, and a reclaim outside an uptrend, inside the blocked hours or before the rule was
switched on never buys. A short line
(60 minutes, 10-minute dwell) keeps the candle counts small; the full-size rule is checked against the backtest by
`stage2_backtesting/scripts/verify_pullback_parity.py`.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.strategy import load_strategies, validate_strategy
from app.domain.pullback import PullbackConfig, PullbackState, replay, step
from app.services.binance_client import BinanceClient
from app.services.binance_exchange import BinanceExchange
from app.services.live_execution_service import LiveExecutionService
from app.services.pullback_service import PullbackService
from test_trend_exit_integration import FakeBinance, candle, database, rows  # noqa: F401  (shared fixture)

SYMBOL = "ETHUSDT"
MINUTE = timedelta(minutes=1)
T0 = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)
RULE = PullbackConfig(ema_minutes=3, dwell_minutes=2)


def minutes(prices, start=T0):
    return [(start + index * MINUTE, Decimal(str(price))) for index, price in enumerate(prices)]


# ------------------------------------------------------------------ the rule
def test_a_reclaim_needs_the_full_dwell_below_the_line():
    _, found = replay(minutes([100, 100, 99, 100.5]), RULE)
    assert found == [], "one minute below is not a pullback"
    _, found = replay(minutes([100, 100, 99, 99, 100.5]), RULE)
    assert [r.reclaim_at for r in found] == [T0 + 4 * MINUTE]
    reclaim = found[0]
    assert reclaim.below_minutes == 2 and reclaim.below_since == T0 + 2 * MINUTE
    assert reclaim.entry_at == T0 + 5 * MINUTE, "the buy is the minute after the close back above the line"


def test_the_line_includes_the_minutes_own_close():
    # pandas ewm(span=3, adjust=False): alpha 0.5, so 100 -> 100 -> 99.5 after a 99 close.
    state, _ = replay(minutes([100, 100, 99]), RULE)
    assert state.ema == Decimal("99.5") and state.below_minutes == 1


def test_a_close_level_with_the_line_ends_the_pullback():
    state, _ = replay(minutes([100, 100]), RULE)             # line exactly 100
    state, reclaim = step(state, T0 + 2 * MINUTE, Decimal("100"), RULE)
    assert reclaim is None and state.below_minutes == 0, "below means strictly below"


def test_a_missing_minute_ends_the_run_instead_of_bridging_it():
    state, _ = replay(minutes([100, 100, 99]), RULE)
    state, _ = step(state, T0 + 4 * MINUTE, Decimal("99"), RULE)     # minute 3 never arrived
    assert state.below_minutes == 1 and state.below_since == T0 + 4 * MINUTE
    state, reclaim = step(state, T0 + 5 * MINUTE, Decimal("101"), RULE)
    assert reclaim is None, "the gap cut the run to one minute, short of the dwell"


def test_the_state_survives_a_round_trip_through_storage():
    state, _ = replay(minutes([100, 100, 99, 99]), RULE)
    assert PullbackState.from_json(json.loads(json.dumps(state.to_json()))) == state


def test_the_config_comes_from_eth_only():
    strategies = load_strategies()
    eth = PullbackConfig.from_strategy(strategies["ETHUSDT"])
    assert eth == PullbackConfig(ema_minutes=1440, dwell_minutes=180, requires_uptrend=True,
                                 blocked_entry_hours=(6, 12))
    assert eth.blocked(datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc))
    assert not eth.blocked(datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc))
    assert all(PullbackConfig.from_strategy(s) is None for symbol, s in strategies.items() if symbol != "ETHUSDT")


# ------------------------------------------------------------------ end to end
def short_strategy() -> dict:
    strategy = copy.deepcopy(load_strategies()[SYMBOL])
    strategy["entry"]["pullback_to_trend"].update(ema_minutes=60, dwell_minutes=10)
    return validate_strategy(strategy)


def build(database, *, lots=1, uptrend=True, start=T0):
    strategy = short_strategy()
    binance = FakeBinance()
    client = BinanceClient("key", "secret")
    client._request = binance.request  # type: ignore[method-assign]
    execution = LiveExecutionService(database, {SYMBOL: strategy}, BinanceExchange(client, live=True))
    service = PullbackService(database, strategy)
    a7, a15, a30 = (Decimal("210"), Decimal("205"), Decimal("200")) if uptrend else \
                   (Decimal("205"), Decimal("200"), Decimal("210"))
    with database.begin() as connection:
        for table in ("trades", "orders", "positions", "signals", "touch_episodes",
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
            {"v": json.dumps({"trading_mode": "live", "daily_loss_limit_usd": "0", "maximum_open_value_usd": "0",
                              "pot_lots": lots, "pot_lot_size_usd": "100"})})
        connection.execute(
            text("""INSERT INTO daily_averages (symbol, effective_at, completed_through, average_7d, average_15d,
                                                average_30d, signal_average_days, signal_average)
                    VALUES (:s, :at, :day, :a7, :a15, :a30, 7, :a7)"""),
            {"s": SYMBOL, "at": start.replace(hour=0, minute=0), "day": start.date() - timedelta(days=1),
             "a7": a7, "a15": a15, "a30": a30})
    return execution, service, binance, strategy


def play_a_pullback(engine, service, start=T0) -> datetime:
    """200 flat minutes at $200, 12 minutes at $199 (under the line), then a close at $201 back above it.

    The rule is switched on after the flat stretch, like a bot that was already running when the dip came.
    Returns the minute the buy should land on.
    """
    for index in range(200):
        candle(engine, start + index * MINUTE, Decimal("200"))
    service.synchronize()
    for index in range(200, 212):
        candle(engine, start + index * MINUTE, Decimal("199"))
    reclaim = start + 212 * MINUTE
    candle(engine, reclaim, Decimal("201"))
    service.synchronize()
    return reclaim + MINUTE


def dip_signal(engine, strategy_id, at) -> None:
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO touch_episodes (episode_id, strategy_id, symbol, touch_time,
                                       average_value, status) VALUES ('dip1', :id, :s, :t, 200, 'confirmed')"""),
                           {"id": strategy_id, "s": SYMBOL, "t": at})
        connection.execute(text("""INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, entry_time,
                                       status) VALUES ('dip1', 'dip1', :id, :t, :t, 'confirmed')"""),
                           {"id": strategy_id, "t": at})


def test_a_pullback_in_an_uptrend_becomes_a_signal_and_buys_a_lot(database):
    execution, service, binance, _ = build(database, lots=1)
    entry = play_a_pullback(database, service)

    signal = rows(database, "SELECT * FROM signals")[0]
    assert signal["status"] == "confirmed" and signal["entry_time"] == entry
    assert signal["details"]["kind"] == "pullback" and signal["details"]["below_minutes"] == 12

    binance.price = Decimal("201")
    candle(database, entry, Decimal("201"))
    execution.synchronize(SYMBOL)
    lot = rows(database, "SELECT * FROM positions")[0]
    assert lot["entry_source"] == "pullback" and lot["lot_number"] == 1
    assert lot["trend_exit_active"] is True, "bought in an uptrend, so it rides the trend line"
    assert lot["stop_price"] == Decimal("191.9500000000"), "the dip's -4.5% stop"


def test_the_pullback_shares_the_coins_lots_with_the_dip(database):
    """One lot, a dip and a pullback in the same minute: whichever is taken first gets it, the other is skipped."""
    execution, service, binance, strategy = build(database, lots=1)
    entry = play_a_pullback(database, service)
    dip_signal(database, strategy["strategy_id"], entry)
    binance.price = Decimal("201")
    candle(database, entry, Decimal("201"))
    execution.synchronize(SYMBOL)
    assert [row["entry_source"] for row in rows(database, "SELECT * FROM positions")] == ["signal"]
    skipped = rows(database, "SELECT status, reason FROM signals WHERE signal_id LIKE 'pullback:%'")[0]
    assert skipped["status"] == "ignored_not_allowed" and "All 1 shared lots are open" in skipped["reason"]


def test_a_second_lot_lets_both_the_dip_and_the_pullback_in(database):
    execution, service, binance, strategy = build(database, lots=2)
    entry = play_a_pullback(database, service)
    dip_signal(database, strategy["strategy_id"], entry)
    binance.price = Decimal("201")
    candle(database, entry, Decimal("201"))
    execution.synchronize(SYMBOL)
    lots = {row["entry_source"]: row["lot_number"] for row in rows(database, "SELECT * FROM positions")}
    assert lots == {"signal": 1, "pullback": 2}, "one set of lots, numbered in the order they were bought"


def test_a_pullback_outside_an_uptrend_is_not_a_setup(database):
    _, service, _, _ = build(database, uptrend=False)
    play_a_pullback(database, service)
    assert rows(database, "SELECT * FROM signals") == []
    assert rows(database, "SELECT value FROM engine_state WHERE key='pullback:ETHUSDT'")[0]["value"][
        "last_reclaim"]["regime"] == "neutral", "it was seen, and the dashboard can say why it did not count"


def test_a_pullback_in_the_blocked_hours_is_recorded_but_never_bought(database):
    start = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)     # the reclaim lands at 06:32, inside 06-12
    execution, service, binance, _ = build(database, start=start)
    entry = play_a_pullback(database, service, start)
    signal = rows(database, "SELECT status, entry_time FROM signals")[0]
    assert signal == {"status": "skipped_time_window", "entry_time": None}
    binance.price = Decimal("201")
    candle(database, entry, Decimal("201"))
    execution.synchronize(SYMBOL)
    assert rows(database, "SELECT * FROM positions") == []


def test_pullbacks_from_before_the_switch_on_are_never_written(database):
    _, service, _, _ = build(database)
    for index, price in enumerate([200] * 200 + [199] * 12 + [201] + [201] * 5):
        candle(database, T0 + index * MINUTE, Decimal(str(price)))
    status = service.synchronize()          # first start: all of that is history
    assert status["rewarmed"] is True and rows(database, "SELECT * FROM signals") == []


def test_losing_the_stored_state_rewarms_the_line_from_candles(database):
    _, service, _, _ = build(database)
    play_a_pullback(database, service)
    before = rows(database, "SELECT value FROM engine_state WHERE key='pullback:ETHUSDT'")[0]["value"]
    with database.begin() as connection:
        connection.execute(text("""UPDATE engine_state SET value = value - 'state' WHERE key='pullback:ETHUSDT'"""))
    after = service.synchronize()
    assert after["rewarmed"] is True
    assert Decimal(after["line"]) == Decimal(before["line"]), "the same candles give the same line"
    assert len(rows(database, "SELECT * FROM signals")) == 1, "re-reading history never duplicates a signal"
