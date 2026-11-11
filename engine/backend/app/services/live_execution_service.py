"""Trading the strategies with real money on Binance.

One coin at a time, driven by closed one-minute candles:

1. exits first  - a protective stop already sits on Binance; the trailing stop is decided here and sold at market
2. entries next - a confirmed signal buys exactly one lot with a market order, then a stop is parked on Binance
3. book-keeping - real fills, real fees, and a snapshot of the wallet

Money is never held by this app: lot sizes are checked against the free USDT in the Binance spot wallet. In
"shadow" mode every order is prepared and recorded but not sent, so the strategy can be watched before it trades.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.domain import trend
from app.domain.paper_execution import (
    BREAKOUT, MODULES, PULLBACK, PYRAMID, Candle, CoinAllocation, ExecutionConfig, Position,
    evaluate_exit, manual_exit_signal, uses_trend_exit,
)
from app.domain.pyramid import PyramidConfig, wants_add
from app.services.binance_client import BinanceError
from app.services.binance_exchange import BinanceExchange, OrderResult, order_id_for

MONEY = Decimal("0.00000001")
PRICE = Decimal("0.0000000001")
QUANTITY = Decimal("0.000000000001")
ZERO = Decimal("0")
ONE_MINUTE = timedelta(minutes=1)
STATE_KEY = "live_execution"
SETTINGS_KEY = "account_settings"
TICKER_CACHE_SECONDS = 120
BALANCE_CACHE_SECONDS = 10
# Binance rejects an order whose value is below its minimum; a lot must also cover its own fees comfortably.
# No money is assumed: the pot is empty and the loss limit off until the user sets them (or sets a shadow amount).
DEFAULT_SETTINGS = {"trading_mode": "shadow", "daily_loss_limit_usd": "0", "maximum_open_value_usd": "0",
                    "pot_lots": 0, "pot_lot_size_usd": "0", "shadow_start_usd": "0"}


@dataclass(frozen=True)
class SharedPot:
    """One set of lots shared by every coin that is switched on, first come first served.

    No coin owns money or slots: any coin's signal buys while one of the `lots` is free and Binance has USDT. The
    last lot takes whatever cash is left after losses (see affordable_lot), and profit refills lots to full size.
    """
    lots: int
    lot_size_usd: Decimal

    @property
    def total_usd(self) -> Decimal:
        return self.lot_size_usd * self.lots


def read_pot(connection: Connection) -> SharedPot:
    settings = read_settings(connection)
    return SharedPot(int(settings.get("pot_lots") or 0), Decimal(str(settings.get("pot_lot_size_usd") or "0")))


def suggested_pot(value: Decimal, minimum_lot: Decimal = Decimal("10")) -> SharedPot | None:
    """The growth plan for this much money, for any amount.

    From $300 it is the tested plan: 3 x $100, one more lot per extra $100 up to 5 lots, then +$20 on every lot
    per extra $100 (so $1,000 -> 5 x $200). Below $300: 3 equal lots in whole dollars. None when 3 lots would be
    under the minimum lot size.
    """
    if value < 3 * minimum_lot:
        return None
    if value < 300:
        return SharedPot(3, (value / 3).quantize(Decimal("1"), rounding="ROUND_DOWN"))
    steps = int((value - 300) // 100)
    if steps <= 2:
        return SharedPot(3 + steps, Decimal("100"))
    return SharedPot(5, Decimal(100 + 20 * (steps - 2)))


def open_lot_total(connection: Connection) -> int:
    """Open lots across every coin: they all come out of the one shared pot."""
    return int(connection.execute(text("SELECT count(*) FROM paper_positions WHERE status='open'")).scalar_one())


def affordable_lot(lot: Decimal, free_usdt: Decimal) -> Decimal | None:
    """What one lot spends: the full lot, or - when the pot has less - whatever free USDT is left (cents only).

    Coins share one pot, so the coin that buys last takes what the others left. Binance's own minimum order value
    (about $5) still applies and is checked before the order is sent.
    """
    if free_usdt >= lot:
        return lot
    left = free_usdt.quantize(Decimal("0.01"), rounding="ROUND_DOWN")
    return left if left > 0 else None


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY)


def price(value: Decimal) -> Decimal:
    return value.quantize(PRICE)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY)


def coin_label(symbol: str) -> str:
    return symbol.removesuffix("USDT")


def read_settings(connection: Connection) -> dict:
    value = connection.execute(
        text("SELECT value FROM engine_state WHERE key=:key"), {"key": SETTINGS_KEY}
    ).scalar_one_or_none()
    return {**DEFAULT_SETTINGS, **(value or {})}


def read_allocation(connection: Connection, symbol: str) -> CoinAllocation | None:
    row = connection.execute(
        text("""SELECT dip_enabled, breakout_enabled, pullback_enabled, pyramid_enabled
                FROM coin_allocations WHERE symbol=:symbol"""),
        {"symbol": symbol},
    ).mappings().one_or_none()
    if not row:
        return None
    return CoinAllocation(frozenset(name for name in MODULES if row[f"{name}_enabled"]))


# Which signal kind opens which kind of lot. All of them draw on the coin's one set of lots.
SOURCES_BY_KIND = {"consolidation": BREAKOUT, "pullback": PULLBACK}


def read_trading_enabled(connection: Connection, symbol: str) -> bool:
    """A coin trades only once it has been switched on; a coin the bot has never seen stays off."""
    value = connection.execute(
        text("SELECT trading_enabled FROM coin_allocations WHERE symbol=:symbol"), {"symbol": symbol}
    ).scalar_one_or_none()
    return value is True


def shadow_account(connection: Connection, settings: dict) -> dict | None:
    """The pretend wallet shadow mode trades with: the starting amount the user set, plus shadow trades' results.

    Only shadow lots count (no Binance order id). None when no starting amount is set: shadow buys are then not
    limited by money, and the dashboard asks for an amount.
    """
    start = Decimal(str(settings.get("shadow_start_usd") or "0"))
    if start <= ZERO:
        return None
    realized = connection.execute(
        text("""SELECT COALESCE(sum(t.net_pnl_usd), 0) FROM paper_trades t
                JOIN paper_positions p ON p.position_id = t.position_id WHERE p.entry_order_id IS NULL""")
    ).scalar_one()
    rows = connection.execute(
        text("SELECT symbol, quantity, allocation_usd FROM paper_positions WHERE status='open' AND entry_order_id IS NULL")
    ).mappings().all()
    open_cost = sum((row["allocation_usd"] for row in rows), ZERO)
    open_value = sum((row["quantity"] * (latest_price(connection, row["symbol"]) or ZERO) for row in rows), ZERO)
    free = start + realized - open_cost
    return {"start": start, "free": free, "open_value": open_value, "open_cost": open_cost, "realized": realized,
            "wallet": free + open_value, "pnl": realized + open_value - open_cost}


def latest_price(connection: Connection, symbol: str, at: datetime | None = None) -> Decimal | None:
    return connection.execute(
        text("""SELECT close FROM candles_1m WHERE symbol=:symbol
                AND (CAST(:at AS timestamptz) IS NULL OR open_time <= CAST(:at AS timestamptz))
                ORDER BY open_time DESC LIMIT 1"""),
        {"symbol": symbol, "at": at},
    ).scalar_one_or_none()


@dataclass
class CoinSetup:
    symbol: str
    label: str
    strategy: dict
    strategy_id: str
    config: ExecutionConfig
    pyramid: PyramidConfig | None = None

    @classmethod
    def from_strategy(cls, strategy: dict) -> "CoinSetup":
        symbol = strategy["market"]["symbol"]
        return cls(symbol, coin_label(symbol), strategy, strategy["strategy_id"],
                   ExecutionConfig.from_strategy(strategy), PyramidConfig.from_strategy(strategy))


class LiveExecutionService:
    def __init__(self, engine: Engine, strategies: dict[str, dict], exchange: BinanceExchange) -> None:
        self.engine = engine
        self.exchange = exchange
        self.coins = {symbol: CoinSetup.from_strategy(strategy) for symbol, strategy in strategies.items()}
        self._balances: tuple[float, dict[str, Decimal], dict[str, Decimal]] | None = None
        self._tickers: dict[str, tuple[float, Decimal]] = {}
        self._balances_unknown = False

    # ------------------------------------------------------------------ public
    def synchronize(self, symbol: str | None = None) -> dict:
        """Bring one coin (or all of them) up to date with the candles already stored."""
        for coin_symbol in ([symbol] if symbol else list(self.coins)):
            if coin_symbol in self.coins:
                self._advance(coin_symbol)
        self._write_snapshot()
        return self.status()

    def status(self) -> dict:
        with self.engine.connect() as connection:
            state = connection.execute(
                text("SELECT value FROM engine_state WHERE key=:key"), {"key": STATE_KEY}
            ).scalar_one_or_none() or {}
            open_positions = connection.execute(
                text("SELECT count(*) FROM paper_positions WHERE status='open'")
            ).scalar_one()
            snapshot = connection.execute(
                text("SELECT * FROM account_snapshots ORDER BY timestamp DESC LIMIT 1")
            ).mappings().one_or_none()
        return {"state": state, "open_positions": open_positions, "trading_mode": self.trading_mode(),
                "account": dict(snapshot) if snapshot else None}

    def trading_mode(self) -> str:
        with self.engine.connect() as connection:
            return str(read_settings(connection).get("trading_mode", "shadow"))

    # ------------------------------------------------------------------ wallet
    def _load_balances(self, refresh: bool) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
        """Free and locked balances from Binance, cached for a few seconds (and dropped after every order)."""
        import time as _time
        if not refresh and self._balances and _time.monotonic() - self._balances[0] < BALANCE_CACHE_SECONDS:
            return self._balances[1], self._balances[2]
        try:
            account = self.exchange.client.account()
        except BinanceError:
            self._balances_unknown = self._balances is None
            return (self._balances[1], self._balances[2]) if self._balances else ({}, {})
        self._balances_unknown = False
        rows = account.get("balances", [])
        free = {row["asset"]: Decimal(str(row["free"])) for row in rows}
        locked = {row["asset"]: Decimal(str(row.get("locked", "0"))) for row in rows}
        self._balances = (_time.monotonic(), free, locked)
        return free, locked

    def balances(self, refresh: bool = False) -> dict[str, Decimal]:
        """What can be spent or sold right now."""
        return self._load_balances(refresh)[0]

    def holdings(self, refresh: bool = False) -> dict[str, Decimal]:
        """Everything owned, including coins locked in a parked stop order."""
        free, locked = self._load_balances(refresh)
        return {asset: free.get(asset, ZERO) + locked.get(asset, ZERO) for asset in set(free) | set(locked)}

    def free_usdt(self) -> Decimal:
        return self.balances().get("USDT", ZERO)

    # ------------------------------------------------------------------ per coin
    def _advance(self, symbol: str) -> None:
        coin = self.coins[symbol]
        with self.engine.begin() as connection:
            state = self._lock_state(connection)
            coin_state = dict(state.get(symbol) or {})
            if not coin_state.get("last_open_time"):
                # First run for this coin: start at the newest candle instead of replaying stored history.
                newest = connection.execute(
                    text("SELECT max(open_time) FROM candles_1m WHERE symbol=:symbol"), {"symbol": symbol}
                ).scalar_one()
                if newest is None:
                    return
                coin_state["last_open_time"] = (newest - ONE_MINUTE).isoformat()
                state[symbol] = coin_state
                self._write_state(connection, state)
                self._event(connection, "INFO", "coin_started",
                            {"symbol": symbol, "from": coin_state["last_open_time"]})
            last = datetime.fromisoformat(coin_state["last_open_time"])
            candles = connection.execute(
                text("""SELECT open_time, open, high, low, close FROM candles_1m
                        WHERE symbol=:symbol AND (CAST(:last AS timestamptz) IS NULL OR open_time > CAST(:last AS timestamptz))
                        ORDER BY open_time LIMIT 240"""),
                {"symbol": symbol, "last": last},
            ).mappings().all()
            if not candles:
                return
            for row in candles:
                candle = Candle(**dict(row))
                ema = self._advance_ema(connection, coin, candle, coin_state)
                self._manage_open_positions(connection, coin, candle, ema)
                self._take_entries(connection, coin, candle)
                # Adds come after the ordinary entries, so a parent bought this minute can be added to later,
                # never in the same minute it was bought.
                self._take_pyramid_adds(connection, coin, candle, ema)
                coin_state["last_open_time"] = candle.open_time.isoformat()
            coin_state["checked_at"] = datetime.now(timezone.utc).isoformat()
            state[symbol] = coin_state
            self._write_state(connection, state)

    def _advance_ema(self, connection: Connection, coin: CoinSetup, candle: Candle,
                     coin_state: dict) -> Decimal | None:
        """The trend line for this minute, including this minute's close.

        The running value lives in the coin's state so a restart does not reset it. If the state is
        missing or out of step with this candle, it is warmed up again from stored candles.
        """
        minutes = coin.config.trend_exit_ema_minutes
        if minutes is None:
            return None
        stored, stored_at = coin_state.get("ema"), coin_state.get("ema_at")
        previous: Decimal | None = None
        if stored is not None and stored_at == (candle.open_time - ONE_MINUTE).isoformat():
            previous = Decimal(str(stored))
        else:
            closes = connection.execute(
                text("""SELECT close FROM candles_1m WHERE symbol=:symbol AND open_time < :t
                        ORDER BY open_time DESC LIMIT :window"""),
                {"symbol": coin.symbol, "t": candle.open_time, "window": trend.warmup_minutes(minutes)},
            ).scalars().all()
            previous = trend.seed([Decimal(str(value)) for value in reversed(closes)], minutes)
            if stored is not None:
                self._event(connection, "INFO", "trend_line_rewarmed",
                            {"symbol": coin.symbol, "minutes": minutes, "candles": len(closes)})
        value = trend.advance(previous, candle.close, minutes)
        coin_state["ema"] = str(value)
        coin_state["ema_at"] = candle.open_time.isoformat()
        return value

    # ------------------------------------------------------------------ exits
    def _manage_open_positions(self, connection: Connection, coin: CoinSetup, candle: Candle,
                               ema: Decimal | None = None) -> None:
        positions = self._open_positions(connection, coin.symbol)
        # On this coin an add may have no exit of its own: it is sold the moment its parent is. Parents are
        # bought before their adds, so a parent sold in this pass is already in `gone` when its adds come up.
        follows_parent = coin.pyramid is not None and coin.pyramid.follows_parent
        still_open = {row["position_id"] for _, row in positions}
        gone: dict[str, str] = {}
        for position, row in positions:
            parent_id = row["parent_position_id"] if follows_parent else None
            if row["stop_order_id"] and self.exchange.live:
                filled = self._stop_order_filled(connection, coin, position, row)
                if filled:
                    gone[position.position_id] = "protective_stop"
                    continue
            if parent_id:
                if parent_id in gone or parent_id not in still_open:
                    # The parent has left, so its add goes with it - at this minute's price.
                    self._sell(connection, coin, position, row, "parent_exit", candle)
                else:
                    self._save_position_state(connection, position)
                continue
            armed_before = row["trailing_active"]
            signal = evaluate_exit(position, candle, coin.config, ema)
            if signal is None and position.trailing_active and not armed_before:
                # It just armed. A trend-ride lot now rides the line, so its stop moves up to break even plus
                # costs - and the order Binance holds has to be moved with it, or the floor only exists here.
                self._raise_stop_to_break_even(connection, coin, position, row)
            close_request = self._pending_close(connection, position.position_id)
            if signal is None and close_request:
                signal = manual_exit_signal(position, candle, close_request["requested_at"])
            if signal is None:
                self._save_position_state(connection, position)
                continue
            if (signal.reason in ("protective_stop", "ambiguous_stop", "break_even")
                    and row["stop_order_id"] and self.exchange.live):
                # Binance's own stop order handles this; the next cycle records the fill.
                self._save_position_state(connection, position)
                continue
            if self._sell(connection, coin, position, row, signal.reason, candle):
                gone[position.position_id] = signal.reason
            if close_request:
                self._finish_request(connection, close_request["request_id"], "applied",
                                     details={"exit_reason": signal.reason})

    def _stop_order_filled(self, connection: Connection, coin: CoinSetup, position: Position, row) -> bool:
        """Did Binance's parked stop order sell this lot?"""
        try:
            order = self.exchange.order_status(coin.symbol, row["stop_order_id"])
        except BinanceError as error:
            self._event(connection, "WARNING", "stop_order_unreadable",
                        {"symbol": coin.symbol, "position_id": position.position_id, "error": error.explanation})
            return False
        if order.get("status") != "FILLED":
            return False
        sold = Decimal(str(order.get("executedQty", "0")))
        received = Decimal(str(order.get("cummulativeQuoteQty", "0")))
        fee, asset = self._trade_fees(coin.symbol, str(order.get("orderId")))
        exit_price = received / sold if sold > ZERO else ZERO
        fee_usd = self._fee_in_usd(connection, fee, asset, coin.symbol)
        self._record_execution_observation(
            connection, coin.symbol, position.position_id, "sell", "filled_stop", None, None,
            datetime.now(timezone.utc), None, None, row.get("stop_price"), exit_price,
            None, fee_usd, asset, received, None, str(order.get("orderId")), False, None,
            {"order_type": "STOP_LOSS_LIMIT"},
        )
        self._record_exit(connection, coin, position, row, "protective_stop", sold, received, fee, asset,
                          str(order.get("orderId")))
        return True

    def _sell(self, connection: Connection, coin: CoinSetup, position: Position, row, reason: str,
              candle: Candle) -> bool:
        """Cancel the parked stop (if any) and sell at market. True when the exit was recorded."""
        if row["stop_order_id"]:
            cancel = self.exchange.cancel(coin.symbol, row["stop_order_id"])
            self._record_exchange_event(connection, coin.symbol, "cancel_stop", position.position_id, cancel)
        rules = self.exchange.rules(coin.symbol) if self.exchange.live else None
        available = self.balances(refresh=True).get(coin.label, position.quantity) if self.exchange.live else position.quantity
        amount = min(position.quantity, available) if self.exchange.live else position.quantity
        if rules:
            problem = rules.rejects_sell(amount, candle.close)
            if problem:
                self._event(connection, "ERROR", "sell_rejected",
                            {"symbol": coin.symbol, "position_id": position.position_id, "reason": problem})
                return False
        decision_at = datetime.now(timezone.utc)
        bid, ask = self._decision_quote(coin.symbol)
        requested_at, started = datetime.now(timezone.utc), time.monotonic()
        result = self.exchange.market_sell(coin.symbol, amount, client_order_id=order_id_for("x", position.position_id))
        completed_at = datetime.now(timezone.utc)
        latency_ms = (time.monotonic() - started) * 1000
        self._record_exchange_event(connection, coin.symbol, "market_sell", position.position_id, result)
        if not result.ok:
            self._record_execution_observation(
                connection, coin.symbol, position.position_id, "sell", "rejected", decision_at, requested_at,
                completed_at, bid, ask, candle.open, None, latency_ms, None, None, None,
                result.client_order_id, result.exchange_order_id, result.recovered, result.error, {},
            )
            self._event(connection, "ERROR", "sell_failed",
                        {"symbol": coin.symbol, "position_id": position.position_id, "error": result.error})
            return False
        if result.sent:
            sold, received = result.filled_quantity, result.filled_quote
            fee, asset = result.commission()
        else:  # shadow: value the lot at the candle close
            sold, received = amount, amount * candle.close
            fee, asset = received * coin.config.usdt_fee_bps / Decimal("10000"), "USDT"
        exit_price = received / sold if sold > ZERO else ZERO
        fee_usd = self._fee_in_usd(connection, fee, asset, coin.symbol)
        self._record_execution_observation(
            connection, coin.symbol, position.position_id, "sell", "filled" if result.sent else "shadow",
            decision_at, requested_at, completed_at, bid, ask, candle.open, exit_price, latency_ms,
            fee_usd, asset, received, result.client_order_id, result.exchange_order_id,
            result.recovered, None, {"exit_reason": reason},
        )
        self._record_exit(connection, coin, position, row, reason, sold, received, fee, asset,
                          result.exchange_order_id, client_order_id=result.client_order_id, shadow=not result.sent)
        return True

    def _record_exit(self, connection: Connection, coin: CoinSetup, position: Position, row, reason: str,
                     sold: Decimal, received: Decimal, fee: Decimal, fee_asset: str, order_id: str | None,
                     client_order_id: str | None = None, shadow: bool = False) -> None:
        exit_price = received / sold if sold > ZERO else ZERO
        fee_usd = self._fee_in_usd(connection, fee, fee_asset, coin.symbol)
        entry_fee_usd = position.entry_fee_usd
        cost = position.allocation_usd
        pnl = received - cost - fee_usd - (entry_fee_usd if position.entry_fee_asset != "USDT" else ZERO)
        now = datetime.now(timezone.utc)
        connection.execute(
            text(
                """
                UPDATE paper_positions SET status='closed', exit_time=:at, raw_exit_price=:price, exit_fill_price=:price,
                    exit_fee_usd=:fee, exit_fee_asset=:asset, exit_cash_usd=:received, exit_reason=:reason,
                    realized_pnl_usd=:pnl, exit_order_id=:order_id, quantity_sold=:sold, trailing_active=:trailing,
                    peak_price=:peak, trailing_started_at=:trail_at, bars_held=:bars, updated_at=now()
                WHERE position_id=:id
                """
            ),
            {"id": position.position_id, "at": now, "price": price(exit_price), "fee": money(fee_usd),
             "asset": fee_asset, "received": money(received), "reason": reason, "pnl": money(pnl),
             "order_id": order_id, "sold": quantity(sold), "trailing": position.trailing_active,
             "peak": price(position.peak_price) if position.peak_price else None,
             "trail_at": position.trailing_started_at, "bars": position.bars_held},
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_orders (order_id, position_id, side, status, requested_at, raw_price, fill_price,
                    quantity, notional_usd, fee_usd, fee_asset, fee_bnb, slippage_usd, exchange_order_id,
                    client_order_id, order_type, fee_asset_quantity)
                VALUES (:id, :position_id, 'sell', :status, :at, :price, :price, :qty, :notional, :fee, :asset,
                        :fee_bnb, 0, :order_id, :client_order_id, :type, :fee_qty)
                ON CONFLICT (order_id) DO NOTHING
                """
            ),
            {"id": f"sell:{position.position_id}", "position_id": position.position_id,
             "status": "shadow" if shadow else "filled", "at": now, "price": price(exit_price),
             "qty": quantity(sold), "notional": money(received), "fee": money(fee_usd), "asset": fee_asset,
             "fee_bnb": quantity(fee) if fee_asset == "BNB" else ZERO, "order_id": order_id,
             "client_order_id": client_order_id, "type": "MARKET", "fee_qty": quantity(fee)},
        )
        held = int((now - position.entry_time).total_seconds() // 60)
        connection.execute(
            text(
                """
                INSERT INTO paper_trades (trade_id, position_id, symbol, entry_source, entry_time, exit_time, quantity,
                    allocation_usd, entry_fill_price, exit_fill_price, entry_fee_usd, exit_fee_usd, bnb_fees_usd,
                    slippage_usd, exit_reason, exit_mode, duration_minutes, net_return_pct, net_pnl_usd)
                VALUES (:id, :position_id, :symbol, :source, :entry_time, :exit_time, :qty, :cost, :entry_price,
                        :exit_price, :entry_fee, :exit_fee, :bnb_fees, 0, :reason, :mode, :duration, :ret, :pnl)
                ON CONFLICT (trade_id) DO NOTHING
                """
            ),
            {"id": f"trade:{position.position_id}", "position_id": position.position_id, "symbol": coin.symbol,
             "source": row["entry_source"], "entry_time": position.entry_time, "exit_time": now,
             "qty": quantity(sold), "cost": money(cost), "entry_price": position.entry_fill_price,
             "exit_price": price(exit_price), "entry_fee": money(entry_fee_usd), "exit_fee": money(fee_usd),
             "bnb_fees": money((entry_fee_usd if position.entry_fee_asset == "BNB" else ZERO) +
                               (fee_usd if fee_asset == "BNB" else ZERO)),
             "reason": reason, "duration": max(held, 0), "ret": pnl / cost * 100 if cost else ZERO,
             "pnl": money(pnl),
             # Which way the lot was being held: riding the trend line, or trailing a giveback.
             "mode": "trend" if uses_trend_exit(position, coin.config.for_source(row["entry_source"]))
                     else "giveback"},
        )
        self._event(connection, "INFO", "position_closed",
                    {"symbol": coin.symbol, "position_id": position.position_id, "reason": reason,
                     "pnl_usd": str(money(pnl)), "shadow": shadow})

    # ------------------------------------------------------------------ entries
    def _take_entries(self, connection: Connection, coin: CoinSetup, candle: Candle) -> None:
        signals = connection.execute(
            text(
                """
                SELECT s.signal_id, COALESCE(s.details->>'kind', 'touch') AS kind FROM signals s
                LEFT JOIN paper_positions p ON p.signal_id = s.signal_id
                WHERE s.status='confirmed' AND s.strategy_id=:strategy AND s.entry_time=:t AND p.position_id IS NULL
                ORDER BY s.signal_id FOR UPDATE OF s
                """
            ),
            {"strategy": coin.strategy_id, "t": candle.open_time},
        ).mappings().all()
        manual = self._pending(connection, "manual_buy", coin.symbol)
        # The trend regime is read now, at the buy, not when the touch happened days or hours earlier.
        # The backtest this strategy was validated against does the same, and a stale regime would put a lot
        # into the wrong exit mode for its whole life.
        regime = (self._regime(connection, coin)
                  if (signals or manual) and coin.config.trend_exit_ema_minutes else None)
        for row in signals:
            source = SOURCES_BY_KIND.get(row["kind"], "signal")
            self._buy(connection, coin, candle, signal_id=row["signal_id"], regime=regime, source=source)
        for request in manual:
            # Pressed during this minute: buy at its close, not the one after.
            if request["requested_at"] < candle.exit_time:
                position_id = self._buy(connection, coin, candle, request_id=request["request_id"],
                                        regime=regime)
                self._finish_request(connection, request["request_id"], "applied" if position_id else "rejected",
                                     reason=None if position_id else self._last_block_reason,
                                     details={"position_id": position_id} if position_id else {})

    def _take_pyramid_adds(self, connection: Connection, coin: CoinSetup, candle: Candle,
                           ema: Decimal | None) -> None:
        """Add a lot to any open lot that has climbed another step while it is still above the trend line."""
        rule = coin.pyramid
        if rule is None or ema is None:
            return
        allocation = read_allocation(connection, coin.symbol)
        if allocation is None or not allocation.allows(PYRAMID):
            return
        rows = connection.execute(
            text("""SELECT p.position_id, p.entry_fill_price, p.stop_price,
                           (SELECT count(*) FROM paper_positions a WHERE a.parent_position_id = p.position_id) AS adds
                    FROM paper_positions p
                    WHERE p.symbol=:s AND p.status='open' AND p.entry_source <> 'pyramid'
                    ORDER BY p.entry_time"""),
            {"s": coin.symbol},
        ).mappings().all()
        for row in rows:
            if not wants_add(rule, row["entry_fill_price"], int(row["adds"]), candle.close, ema, candle.exit_time):
                continue
            self._buy(connection, coin, candle, regime="bullish", source=PYRAMID,
                      parent_position_id=row["position_id"], suffix=f"{int(row['adds']) + 1}",
                      # An add that leaves with its parent parks the PARENT's stop, not one measured from its
                      # own higher fill, so the pair really does end together.
                      stop_price=row["stop_price"] if rule.follows_parent else None)

    def _regime(self, connection: Connection, coin: CoinSetup) -> str | None:
        """The trend regime right now, for a lot opened by hand rather than by a signal."""
        row = connection.execute(
            text("""SELECT average_7d, average_15d, average_30d FROM daily_averages
                    WHERE symbol=:s ORDER BY effective_at DESC LIMIT 1"""),
            {"s": coin.symbol},
        ).mappings().one_or_none()
        if not row or None in (row["average_7d"], row["average_15d"], row["average_30d"]):
            return None
        a7, a15, a30 = row["average_7d"], row["average_15d"], row["average_30d"]
        return "bullish" if a7 > a15 > a30 else "bearish" if a7 < a15 < a30 else "neutral"

    def _buy(self, connection: Connection, coin: CoinSetup, candle: Candle, signal_id: str | None = None,
             request_id: str | None = None, regime: str | None = None, source: str | None = None,
             parent_position_id: str | None = None, suffix: str | None = None,
             stop_price: Decimal | None = None) -> str | None:
        source = source or ("signal" if signal_id else "manual")
        allowed, reason, lot = self._entry_allowed(connection, coin, source)
        self._last_block_reason = reason
        if not allowed:
            if signal_id:
                connection.execute(
                    text("""UPDATE signals SET status='ignored_not_allowed', reason=:reason,
                            details = details || CAST(:details AS jsonb) WHERE signal_id=:id"""),
                    {"id": signal_id, "reason": (reason or "")[:100], "details": json.dumps({"blocked": reason})},
                )
            return None
        rules = self.exchange.rules(coin.symbol) if self.exchange.live else None
        if rules:
            problem = rules.rejects_buy(lot)
            if problem:
                self._event(connection, "WARNING", "buy_rejected", {"symbol": coin.symbol, "reason": problem})
                self._last_block_reason = problem
                return None
        position_id = (f"position:add:{parent_position_id}:{suffix}" if parent_position_id
                       else f"position:{signal_id or request_id}")
        decision_at = datetime.now(timezone.utc)
        bid, ask = self._decision_quote(coin.symbol)
        requested_at, started = datetime.now(timezone.utc), time.monotonic()
        result = self.exchange.market_buy(coin.symbol, lot, client_order_id=order_id_for("b", position_id))
        completed_at = datetime.now(timezone.utc)
        latency_ms = (time.monotonic() - started) * 1000
        self._record_exchange_event(connection, coin.symbol, "market_buy", position_id, result)
        if not result.ok:
            self._record_execution_observation(
                connection, coin.symbol, position_id, "buy", "rejected", decision_at, requested_at,
                completed_at, bid, ask, candle.open, None, latency_ms, None, None, None,
                result.client_order_id, result.exchange_order_id, result.recovered, result.error,
                {"source": source},
            )
            self._event(connection, "ERROR", "buy_failed", {"symbol": coin.symbol, "error": result.error})
            self._last_block_reason = result.error
            return None
        if result.sent:
            bought, spent = result.filled_quantity, result.filled_quote
            fee, fee_asset = result.commission()
        else:  # shadow: fill at this candle's close
            spent = lot
            bought = lot / candle.close if candle.close > ZERO else ZERO
            fee, fee_asset = spent * coin.config.usdt_fee_bps / Decimal("10000"), "USDT"
        if bought <= ZERO:
            return None
        fill_price = spent / bought
        fee_usd = self._fee_in_usd(connection, fee, fee_asset, coin.symbol)
        self._record_execution_observation(
            connection, coin.symbol, position_id, "buy", "filled" if result.sent else "shadow",
            decision_at, requested_at, completed_at, bid, ask, candle.open, fill_price, latency_ms,
            fee_usd, fee_asset, spent, result.client_order_id, result.exchange_order_id,
            result.recovered, None, {"source": source},
        )
        # A BNB fee leaves the coin quantity intact; a fee taken in the coin itself reduces what we can sell.
        sellable = bought - fee if fee_asset == coin.label else bought
        lot_number = self._open_lot_count(connection, coin.symbol) + 1
        connection.execute(
            text(
                """
                INSERT INTO paper_positions (position_id, symbol, signal_id, entry_source, lot_number, status,
                    entry_time, raw_entry_price, entry_fill_price, quantity, allocation_usd, entry_fee_usd,
                    entry_fee_asset, entry_fee_bnb, entry_order_id, trend_exit_active, parent_position_id)
                VALUES (:id, :symbol, :signal_id, :source, :lot, 'open', :at, :raw, :fill, :qty, :cost, :fee,
                        :asset, :fee_bnb, :order_id, :trend_exit, :parent)
                """
            ),
            {"id": position_id, "symbol": coin.symbol, "signal_id": signal_id,
             "source": source, "lot": lot_number,
             "at": datetime.now(timezone.utc), "raw": price(candle.close), "fill": price(fill_price),
             "qty": quantity(sellable), "cost": money(spent), "fee": money(fee_usd), "asset": fee_asset,
             "fee_bnb": quantity(fee) if fee_asset == "BNB" else ZERO, "order_id": result.exchange_order_id,
             "parent": parent_position_id,
             # A pyramid add is only ever bought into a climb, so it rides the line - unless its exit
             # belongs to its parent, in which case it has no exit rules of its own at all.
             "trend_exit": coin.config.trend_exit_ema_minutes is not None and stop_price is None
             and (source == PYRAMID or regime == "bullish" or not coin.config.trend_exit_requires_uptrend)},
        )
        connection.execute(
            text(
                """
                INSERT INTO paper_orders (order_id, position_id, side, status, requested_at, raw_price, fill_price,
                    quantity, notional_usd, fee_usd, fee_asset, fee_bnb, slippage_usd, exchange_order_id,
                    client_order_id, order_type, fee_asset_quantity)
                VALUES (:id, :position_id, 'buy', :status, :at, :raw, :fill, :qty, :notional, :fee, :asset,
                        :fee_bnb, 0, :order_id, :client_order_id, 'MARKET', :fee_qty)
                ON CONFLICT (order_id) DO NOTHING
                """
            ),
            {"id": f"buy:{position_id}", "position_id": position_id,
             "status": "shadow" if not result.sent else "filled", "at": datetime.now(timezone.utc),
             "raw": price(candle.close), "fill": price(fill_price), "qty": quantity(bought), "notional": money(spent),
             "fee": money(fee_usd), "asset": fee_asset, "fee_bnb": quantity(fee) if fee_asset == "BNB" else ZERO,
             "order_id": result.exchange_order_id, "client_order_id": result.client_order_id,
             "fee_qty": quantity(fee)},
        )
        self._place_stop(connection, coin, position_id, sellable, fill_price, source, stop_price)
        self._event(connection, "INFO", "position_opened",
                    {"symbol": coin.symbol, "position_id": position_id, "spent_usdt": str(money(spent)),
                     "price": str(price(fill_price)), "shadow": not result.sent})
        return position_id

    def _raise_stop_to_break_even(self, connection: Connection, coin: CoinSetup, position: Position, row) -> None:
        """Move a just-armed trend-ride lot's stop up to its fill plus costs, on Binance as well as here.

        Binance holds one stop per lot and the coin is locked behind it, so the old order has to be cancelled
        before the new one can be placed. If the replacement fails the lot is left unprotected on the exchange,
        so that is logged loudly and the stored level stays where the bot can still act on it.
        """
        config = coin.config.for_source(position.entry_source)
        if not uses_trend_exit(position, config):
            return                                   # A trailing-stop lot keeps its giveback trail; the floor is not for it
        floor = position.entry_fill_price * (1 + config.break_even_floor_pct / 100)
        if row["stop_price"] is not None and Decimal(str(row["stop_price"])) >= floor:
            return
        level = self.exchange.stop_trigger(coin.symbol, floor)
        if self.exchange.live and row["stop_order_id"]:
            cancelled = self.exchange.cancel(coin.symbol, row["stop_order_id"])
            self._record_exchange_event(connection, coin.symbol, "cancel_stop", position.position_id, cancelled)
            if not cancelled.ok:
                self._event(connection, "ERROR", "break_even_stop_not_moved",
                            {"symbol": coin.symbol, "position_id": position.position_id,
                             "error": cancelled.error, "note": "The old stop is still on Binance."})
                return
            # "f" for the floor: a distinct id, because "s" and "b" already name this lot's first stop and buy.
            result = self.exchange.protective_stop(coin.symbol, position.quantity, level,
                                                   client_order_id=order_id_for("f", position.position_id))
            self._record_exchange_event(connection, coin.symbol, "break_even_stop", position.position_id, result)
            if not result.ok:
                self._event(connection, "ERROR", "stop_order_failed",
                            {"symbol": coin.symbol, "position_id": position.position_id, "error": result.error,
                             "note": "The lot is unprotected on Binance; the bot will still sell at break even."})
            connection.execute(
                text("UPDATE paper_positions SET stop_order_id=:order_id, stop_price=:stop WHERE position_id=:id"),
                {"id": position.position_id, "order_id": result.exchange_order_id, "stop": price(level)},
            )
        else:
            connection.execute(text("UPDATE paper_positions SET stop_price=:stop WHERE position_id=:id"),
                               {"id": position.position_id, "stop": price(level)})
        self._event(connection, "INFO", "stop_raised_to_break_even",
                    {"symbol": coin.symbol, "position_id": position.position_id, "stop": str(price(level))})

    def _place_stop(self, connection: Connection, coin: CoinSetup, position_id: str, amount: Decimal,
                    fill_price: Decimal, entry_source: str = "signal", level: Decimal | None = None) -> None:
        """Park the protective stop on Binance so a crash sells even if this app is offline."""
        # Store the trigger Binance really holds (rounded to its price tick), not the unrounded figure.
        # A breakout lot breaks out of a tighter band, so it parks a tighter stop than a dip lot does, and an add
        # that leaves with its parent parks the parent's own level.
        config = coin.config.for_source(entry_source)
        stop_price = self.exchange.stop_trigger(coin.symbol, level if level is not None
                                                else fill_price * (1 - config.stop_pct / 100))
        result = self.exchange.protective_stop(coin.symbol, amount, stop_price,
                                               client_order_id=order_id_for("s", position_id))
        self._record_exchange_event(connection, coin.symbol, "protective_stop", position_id, result)
        connection.execute(
            text("UPDATE paper_positions SET stop_order_id=:order_id, stop_price=:stop WHERE position_id=:id"),
            {"id": position_id, "order_id": result.exchange_order_id, "stop": price(stop_price)},
        )
        if not result.ok:
            self._event(connection, "ERROR", "stop_order_failed",
                        {"symbol": coin.symbol, "position_id": position_id, "error": result.error,
                         "note": "The lot is unprotected on Binance; the bot will still sell at its stop."})

    def _entry_allowed(self, connection: Connection, coin: CoinSetup,
                       source: str = "signal") -> tuple[bool, str | None, Decimal]:
        settings = read_settings(connection)
        if not read_trading_enabled(connection, coin.symbol):
            return False, f"{coin.label} is switched off.", ZERO
        if settings.get("trading_mode") == "off":
            return False, "All trading is stopped.", ZERO
        pot = read_pot(connection)
        lot = pot.lot_size_usd
        allocation = read_allocation(connection, coin.symbol)
        if allocation is not None and not allocation.allows(source):
            return False, f"The {coin.label} {source} entry is switched off.", lot
        if pot.lots <= 0 or lot <= ZERO:
            return False, "The shared pot has no lots set.", lot
        # Every coin and every way in shares the pot's lots, first come first served.
        if open_lot_total(connection) >= pot.lots:
            return False, f"All {pot.lots} shared lots are open.", lot
        maximum_open = Decimal(str(settings.get("maximum_open_value_usd") or "0"))
        if maximum_open > ZERO:
            total_open = connection.execute(
                text("SELECT COALESCE(sum(allocation_usd),0) FROM paper_positions WHERE status='open'")
            ).scalar_one()
            if total_open + lot > maximum_open:
                return False, f"The ${maximum_open:.0f} limit on money in open trades would be passed.", lot
        limit = Decimal(str(settings.get("daily_loss_limit_usd") or "0"))
        if limit > ZERO and self._today_pnl(connection) <= -limit:
            return False, f"Today's loss limit of ${limit:.0f} has been reached; trading pauses until tomorrow.", lot
        shadow = None if self.exchange.live else shadow_account(connection, settings)
        free = self.free_usdt() if self.exchange.live else shadow["free"] if shadow else lot
        spend = affordable_lot(lot, free)
        if spend is None:
            where = "The shadow wallet" if shadow else "Binance"
            return False, f"{where} has ${free:.2f} free USDT, nothing left to buy with.", lot
        return True, None, spend

    # ------------------------------------------------------------------ helpers
    def _open_positions(self, connection: Connection, symbol: str) -> list[tuple[Position, dict]]:
        rows = connection.execute(
            text(
                """
                SELECT position_id, symbol, entry_time, raw_entry_price, entry_fill_price, quantity, allocation_usd,
                       entry_fee_usd, entry_fee_asset, bars_held, trailing_active, peak_price, trailing_started_at,
                       trend_exit_active, trend_exit_pending, entry_source, stop_order_id, stop_price,
                       parent_position_id
                FROM paper_positions WHERE symbol=:symbol AND status='open' ORDER BY entry_time FOR UPDATE
                """
            ),
            {"symbol": symbol},
        ).mappings().all()
        return [(Position(**{k: row[k] for k in (
            "position_id", "symbol", "entry_time", "raw_entry_price", "entry_fill_price", "quantity",
            "allocation_usd", "entry_fee_usd", "entry_fee_asset", "bars_held", "trailing_active", "peak_price",
            "trailing_started_at", "trend_exit_active", "trend_exit_pending", "entry_source")}), row) for row in rows]

    def _open_lot_count(self, connection: Connection, symbol: str) -> int:
        """Open lots of this coin. Every way in shares them, so there is only one number to count."""
        return int(connection.execute(
            text("SELECT count(*) FROM paper_positions WHERE symbol=:s AND status='open'"), {"s": symbol},
        ).scalar_one())

    def _today_pnl(self, connection: Connection) -> Decimal:
        return connection.execute(
            text("SELECT COALESCE(sum(net_pnl_usd),0) FROM paper_trades WHERE exit_time >= date_trunc('day', now())")
        ).scalar_one()

    def _save_position_state(self, connection: Connection, position: Position) -> None:
        connection.execute(
            text("""UPDATE paper_positions SET bars_held=:bars, trailing_active=:trailing, peak_price=:peak,
                    trailing_started_at=:trail_at, trend_exit_pending=:pending, updated_at=now()
                    WHERE position_id=:id"""),
            {"id": position.position_id, "bars": position.bars_held, "trailing": position.trailing_active,
             "peak": price(position.peak_price) if position.peak_price else None,
             "trail_at": position.trailing_started_at, "pending": position.trend_exit_pending},
        )

    def _pending(self, connection: Connection, kind: str, symbol: str | None = None) -> list[dict]:
        return [dict(row) for row in connection.execute(
            text("""SELECT * FROM control_requests WHERE status='pending' AND kind=:kind
                    AND (CAST(:symbol AS text) IS NULL OR symbol=CAST(:symbol AS text)) ORDER BY requested_at FOR UPDATE"""),
            {"kind": kind, "symbol": symbol},
        ).mappings().all()]

    def _pending_close(self, connection: Connection, position_id: str) -> dict | None:
        row = connection.execute(
            text("""SELECT * FROM control_requests WHERE status='pending' AND kind='close_position'
                    AND position_id=:id LIMIT 1"""),
            {"id": position_id},
        ).mappings().one_or_none()
        return dict(row) if row else None

    def _finish_request(self, connection: Connection, request_id: str, status: str, reason: str | None = None,
                        details: dict | None = None) -> None:
        connection.execute(
            text("""UPDATE control_requests SET status=:status, reason=:reason, processed_at=now(),
                    details = details || CAST(:details AS jsonb) WHERE request_id=:id"""),
            {"id": request_id, "status": status, "reason": (reason or None) and reason[:200],
             "details": json.dumps(details or {}, default=str)},
        )

    def _trade_fees(self, symbol: str, order_id: str) -> tuple[Decimal, str]:
        try:
            trades = self.exchange.my_trades(symbol, order_id)
        except BinanceError:
            return ZERO, "USDT"
        total, asset = ZERO, "USDT"
        for trade in trades:
            total += Decimal(str(trade.get("commission", "0")))
            asset = trade.get("commissionAsset", asset)
        return total, asset

    def _fee_in_usd(self, connection: Connection, fee: Decimal, asset: str, symbol: str) -> Decimal:
        """Value a commission in dollars. A fee we cannot price must be visible, never silently free."""
        if fee <= ZERO:
            return ZERO
        if asset in ("USDT", "USDC"):
            return fee
        price = latest_price(connection, f"{asset}USDT") or self._ticker_price(f"{asset}USDT")
        if price is None:
            self._event(connection, "WARNING", "fee_value_unknown",
                        {"symbol": symbol, "fee": str(fee), "asset": asset,
                         "note": f"No {asset}USDT price, so this fee is recorded as $0 and profit looks "
                                 "slightly better than it is."})
            return ZERO
        return fee * price

    def _ticker_price(self, symbol: str) -> Decimal | None:
        """Binance's current price, asked directly when no candle is stored yet (cached briefly)."""
        import time as _time
        cached = self._tickers.get(symbol)
        if cached and _time.monotonic() - cached[0] < TICKER_CACHE_SECONDS:
            return cached[1]
        try:
            payload = self.exchange.client._request("GET", "/api/v3/ticker/price", {"symbol": symbol})
            price = Decimal(str(payload["price"]))
        except (BinanceError, KeyError, TypeError, ArithmeticError):
            return None
        self._tickers[symbol] = (_time.monotonic(), price)
        return price

    def _record_exchange_event(self, connection: Connection, symbol: str, action: str, position_id: str | None,
                               result: OrderResult) -> None:
        connection.execute(
            text(
                """
                INSERT INTO exchange_events (symbol, action, position_id, client_order_id, exchange_order_id,
                    request, response, ok)
                VALUES (:symbol, :action, :position_id, :client_order_id, :order_id, CAST(:request AS jsonb),
                        CAST(:response AS jsonb), :ok)
                """
            ),
            {"symbol": symbol, "action": action, "position_id": position_id,
             "client_order_id": result.client_order_id, "order_id": result.exchange_order_id,
             "request": json.dumps(result.request, default=str), "response": json.dumps(result.response, default=str),
             "ok": result.ok},
        )
        if result.sent:
            self._balances = None  # the wallet just changed; never value it from a balance read before the order

    def _decision_quote(self, symbol: str) -> tuple[Decimal | None, Decimal | None]:
        if not self.exchange.live or not hasattr(self.exchange, "best_bid_ask"):
            return None, None
        try:
            return self.exchange.best_bid_ask(symbol)
        except (BinanceError, KeyError, TypeError, ArithmeticError):
            return None, None

    @staticmethod
    def _record_execution_observation(
        connection: Connection, symbol: str, position_id: str | None, side: str, status: str,
        decision_at: datetime | None, requested_at: datetime | None, completed_at: datetime | None,
        best_bid: Decimal | None, best_ask: Decimal | None, expected_open: Decimal | None,
        actual_fill: Decimal | None, latency_ms: float | None, fee_usd: Decimal | None,
        fee_asset: str | None, notional: Decimal | None, client_order_id: str | None,
        exchange_order_id: str | None, recovered: bool, rejection: str | None, details: dict,
    ) -> None:
        fee_rate = (fee_usd / notional * Decimal("10000")
                    if fee_usd is not None and notional and notional > ZERO else None)
        quote = best_ask if side == "buy" else best_bid
        impact = None
        if quote and quote > ZERO and actual_fill is not None:
            impact = ((actual_fill / quote - 1) if side == "buy" else (quote / actual_fill - 1)) * Decimal("10000")
        reference_slippage = None
        if expected_open and expected_open > ZERO and actual_fill is not None:
            reference_slippage = ((actual_fill / expected_open - 1) if side == "buy"
                                  else (expected_open / actual_fill - 1)) * Decimal("10000")
        connection.execute(text("""
            INSERT INTO execution_observations
                (symbol, position_id, side, status, decision_at, requested_at, completed_at, best_bid, best_ask,
                 expected_next_open, actual_average_fill, order_latency_ms, fee_asset, fee_usd, fee_rate_bps,
                 price_impact_bps, next_open_slippage_bps, exchange_order_id, client_order_id, recovered_retry,
                 rejection_reason, details)
            VALUES (:symbol, :position_id, :side, :status, :decision_at, :requested_at, :completed_at, :bid, :ask,
                    :expected, :fill, :latency, :fee_asset, :fee_usd, :fee_rate, :impact, :slippage, :exchange_id,
                    :client_id, :recovered, :rejection, CAST(:details AS jsonb))
        """), {
            "symbol": symbol, "position_id": position_id, "side": side, "status": status,
            "decision_at": decision_at, "requested_at": requested_at, "completed_at": completed_at,
            "bid": best_bid, "ask": best_ask, "expected": expected_open, "fill": actual_fill,
            "latency": latency_ms, "fee_asset": fee_asset, "fee_usd": fee_usd, "fee_rate": fee_rate,
            "impact": impact, "slippage": reference_slippage, "exchange_id": exchange_order_id,
            "client_id": client_order_id, "recovered": recovered, "rejection": rejection,
            "details": json.dumps(details, default=str),
        })

    def _lock_state(self, connection: Connection) -> dict:
        connection.execute(
            text("""INSERT INTO engine_state (key, value, updated_at) VALUES (:key, '{}'::jsonb, now())
                    ON CONFLICT (key) DO NOTHING"""),
            {"key": STATE_KEY},
        )
        return dict(connection.execute(
            text("SELECT value FROM engine_state WHERE key=:key FOR UPDATE"), {"key": STATE_KEY}
        ).scalar_one())

    @staticmethod
    def _write_state(connection: Connection, state: dict) -> None:
        connection.execute(
            text("UPDATE engine_state SET value=CAST(:value AS jsonb), updated_at=now() WHERE key=:key"),
            {"key": STATE_KEY, "value": json.dumps(state, default=str)},
        )

    @staticmethod
    def _event(connection: Connection, level: str, event_type: str, details: dict) -> None:
        connection.execute(
            text("""INSERT INTO system_events (level, component, event_type, details)
                    VALUES (:level, 'live_execution', :event_type, CAST(:details AS jsonb))"""),
            {"level": level, "event_type": event_type, "details": json.dumps(details, default=str)},
        )

    # ------------------------------------------------------------------ snapshot
    def _write_snapshot(self) -> None:
        with self.engine.begin() as connection:
            settings = read_settings(connection)
            # Shadow mode with a starting amount records the pretend wallet, so the chart follows it.
            shadow = shadow_account(connection, settings) if settings.get("trading_mode") != "live" else None
        if shadow:
            free, locked = {"USDT": shadow["free"]}, {}
        else:
            free, locked = self._load_balances(refresh=False)
            if self._balances_unknown:
                # Binance did not answer and nothing is cached: an empty read is not an empty wallet. Skip this
                # minute rather than record a $0 wallet that shows as a crash on the chart.
                return
        held = {asset: free.get(asset, ZERO) + locked.get(asset, ZERO) for asset in set(free) | set(locked)}
        with self.engine.begin() as connection:
            settings = read_settings(connection)
            rows = connection.execute(
                text("""SELECT symbol, quantity, allocation_usd FROM paper_positions WHERE status='open'""")
            ).mappings().all()
            open_value = open_cost = ZERO
            for row in rows:
                mark = latest_price(connection, row["symbol"]) or ZERO
                open_value += row["quantity"] * mark
                open_cost += row["allocation_usd"]
            allocated = read_pot(connection).total_usd
            realized = connection.execute(text("SELECT COALESCE(sum(net_pnl_usd),0) FROM paper_trades")).scalar_one()
            fees = connection.execute(
                text("SELECT COALESCE(sum(entry_fee_usd + exit_fee_usd),0) FROM paper_trades")
            ).scalar_one()
            usdt_free, usdt_locked = free.get("USDT", ZERO), locked.get("USDT", ZERO)
            bnb = held.get("BNB", ZERO)
            bnb_price = latest_price(connection, "BNBUSDT") or ZERO
            # The wallet is what Binance holds - USDT plus every traded coin and BNB at market - never USDT plus the
            # ledger's open lots: in shadow mode those lots were never bought, and right after a real buy the USDT
            # figure may still include the money spent.
            coins_value = ZERO
            for symbol in self.coins:
                amount = held.get(coin_label(symbol), ZERO)
                if amount > ZERO:
                    coins_value += amount * (latest_price(connection, symbol) or ZERO)
            if shadow:
                coins_value = shadow["open_value"]
            wallet = usdt_free + usdt_locked + coins_value + bnb * bnb_price
            values = {
                "timestamp": datetime.now(timezone.utc).replace(second=0, microsecond=0),
                "usdt_free": money(usdt_free), "usdt_locked": money(usdt_locked), "bnb_free": quantity(bnb),
                "bnb_value_usd": money(bnb * bnb_price), "allocated_usd": money(allocated),
                "open_position_value_usd": money(open_value), "open_position_cost_usd": money(open_cost),
                "open_positions": len(rows), "realized_pnl_usd": money(realized),
                "unrealized_pnl_usd": money(open_value - open_cost), "strategy_pnl_usd": money(realized + open_value - open_cost),
                "wallet_value_usd": money(wallet), "total_value_usd": money(wallet),
                "drawdown_pct": ZERO, "usdt_fees_usd": money(fees), "bnb_fees_usd": ZERO, "slippage_usd": ZERO,
                "fees_usd": money(fees), "trading_mode": str(settings.get("trading_mode", "shadow")),
            }
            # One row per minute; a later write in the same minute replaces every figure, not just a few.
            updates = ", ".join(f"{key}=EXCLUDED.{key}" for key in values if key != "timestamp")
            connection.execute(
                text(f"""INSERT INTO account_snapshots ({", ".join(values)})
                         VALUES ({", ".join(f":{key}" for key in values)})
                         ON CONFLICT (timestamp) DO UPDATE SET {updates}"""),
                values,
            )
