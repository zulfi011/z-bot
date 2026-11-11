"""Persist health checks and alert lifecycle transitions for the multi-coin live account."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core import credentials
from app.services.live_execution_service import STATE_KEY, coin_label, read_pot, read_settings

# How far back a health check looks for candles. Long enough to spot a real gap, short enough to stay an
# index lookup instead of a scan of every candle ever stored.
RECENT_WINDOW_MINUTES = 180
# How long after the worker starts that price and lag alerts are replaced by a single "catching up" notice.
STARTUP_GRACE = timedelta(minutes=5)
# How long the account must stay behind before it is worth telling anyone. Five feeds rarely deliver the same
# minute at the same instant, so being a minute or two behind for a moment is ordinary. Without this the alert
# flapped - raised and cleared inside a minute - which put a red banner on screen that looked permanent because
# it kept coming back, and could only be got rid of by hand.
LAG_GRACE = timedelta(minutes=3)


# Every alert this service raises. An active alert whose condition is gone is resolved only if its key is listed
# here - a key missing from this list stays on the dashboard forever.
MANAGED = ("market_data_stale", "market_data_gap", "execution_lag", "recovery_failed", "drawdown_limit",
           "bnb_price_stale", "bnb_low", "bnb_empty", "not_live", "daily_loss_limit", "unprotected_positions",
           "starting_up")
LOW_BNB_ROUND_TRIPS = 4


def bnb_round_trip_usd(strategy: dict, lot_size_usd: Decimal) -> Decimal:
    """BNB fee value of one buy + sell of one lot."""
    return lot_size_usd * Decimal(str(strategy["execution_model"]["bnb_fee_bps_per_side"])) * 2 / Decimal("10000")


class MonitoringService:
    def __init__(self, engine: Engine, strategies: dict[str, dict], stale_after_seconds: int,
                 started_at: datetime | None = None) -> None:
        self.engine = engine
        self.strategies = strategies
        self.symbols = list(strategies)
        self.strategy = next(iter(strategies.values()))
        self.fee_symbol = self.strategy["market"]["fee_symbol"]
        self.stale_after_seconds = stale_after_seconds
        self.started_at = started_at

    def synchronize(self) -> dict:
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            # Only the recent window: counting every stored candle read the whole table on every check, which on a
            # small server starved the trading it is meant to watch. Older gaps are repaired by the worker's own
            # backfill, and a coin with nothing in this window is stale by definition.
            markets = {
                row["symbol"]: row for row in connection.execute(
                    text(
                        """
                        SELECT symbol, min(open_time) AS first_open, max(open_time) AS latest_open, count(*) AS candles
                        FROM candles_1m
                        WHERE symbol = ANY(:symbols) AND open_time >= now() - make_interval(mins => :window)
                        GROUP BY symbol
                        """
                    ),
                    {"symbols": [*self.symbols, self.fee_symbol], "window": RECENT_WINDOW_MINUTES},
                ).mappings().all()
            }
            execution = connection.execute(
                text("SELECT value FROM engine_state WHERE key=:key"), {"key": STATE_KEY}
            ).scalar_one_or_none() or {}
            # What the last health check saw, so "how long has this been wrong" survives a restart.
            previous = connection.execute(
                text("SELECT value FROM engine_state WHERE key='monitoring'")
            ).scalar_one_or_none() or {}
            account = connection.execute(
                text("SELECT * FROM account_snapshots ORDER BY timestamp DESC LIMIT 1")
            ).mappings().one_or_none()
            settings = read_settings(connection)

            conditions: dict[str, dict] = {}
            # Only the coins this bot still trades. A coin that has been dropped (LINK) keeps its last cursor in
            # the state forever, and counting it would hold "The bot is behind" open for good - the alert could
            # then only be cleared by hand, which is exactly what it must never need.
            cursors = {symbol: datetime.fromisoformat(value["last_open_time"])
                       for symbol, value in execution.items()
                       if symbol in self.symbols and isinstance(value, dict) and value.get("last_open_time")}
            cursor = min(cursors.values()) if cursors else None
            coin_health: dict[str, dict] = {}
            for symbol in self.symbols:
                label = coin_label(symbol)
                market = markets.get(symbol)
                latest = market["latest_open"] if market else None
                age = (now - latest).total_seconds() if latest else None
                expected = int((latest - market["first_open"]).total_seconds() // 60) + 1 if market else 0
                missing = max(0, expected - market["candles"]) if market else 0
                coin_health[symbol] = {"age_seconds": round(age, 1) if age is not None else None,
                                       "missing_candles": missing, "latest": latest}
                if age is None or age > self.stale_after_seconds:
                    conditions[f"market_data_stale:{symbol}"] = {
                        "severity": "critical", "title": f"{label} prices have stopped updating",
                        "message": f"No new closed {label} candle has arrived recently. The account pauses until prices return.",
                        "details": {"symbol": symbol, "age_seconds": age}}
                if missing:
                    conditions[f"market_data_gap:{symbol}"] = {
                        "severity": "critical", "title": f"Missing {label} candles",
                        "message": f"{missing} one-minute {label} candle(s) are missing; the worker will backfill them.",
                        "details": {"symbol": symbol, "missing_candles": missing}}
            # The account moves one minute at a time for every coin together, so it follows the slowest coin.
            latest_all = [health["latest"] for health in coin_health.values()]
            newest = max((value for value in latest_all if value), default=None)
            lag = int((newest - cursor).total_seconds() // 60) if newest and cursor else None
            behind = cursor is not None and (lag is None or lag > 1)
            # Remember when the account first fell behind, so a brief wobble never raises the alarm.
            behind_since = previous.get("behind_since") if behind else None
            if behind and not behind_since:
                behind_since = now.isoformat()
            if behind and now - datetime.fromisoformat(behind_since) >= LAG_GRACE:
                waiting_for = [coin_label(symbol) for symbol in self.symbols
                               if symbol not in cursors
                               or (coin_health[symbol]["latest"] or cursor) > cursors[symbol] + timedelta(minutes=2)]
                stuck_for = int((now - datetime.fromisoformat(behind_since)).total_seconds() // 60)
                conditions["execution_lag"] = {
                    "severity": "critical", "title": "The bot is behind",
                    "message": f"The account has not processed the latest minute for {stuck_for} minutes"
                               + (f" — waiting for {' and '.join(waiting_for)} prices." if waiting_for else "."),
                    "details": {"lag_minutes": lag, "waiting_for": waiting_for, "behind_since": behind_since}}
            mode = str(settings.get("trading_mode", "shadow"))
            if mode != "live":
                conditions["not_live"] = {
                    "severity": "warning" if mode == "shadow" else "critical",
                    "title": "Trading is not live" if mode == "shadow" else "All trading is stopped",
                    "message": (("The bot is in shadow mode: it works out every order but sends nothing to Binance. "
                                 + ("Switch to Live when you are ready." if credentials.attached()
                                    else "Attach your Binance account to trade for real."))
                                if mode == "shadow" else "Nothing will be bought or sold until you switch trading on."),
                    "details": {"trading_mode": mode}}
            loss_limit = Decimal(str(settings.get("daily_loss_limit_usd") or "0"))
            today = connection.execute(
                text("""SELECT COALESCE(sum(net_pnl_usd),0) FROM paper_trades
                        WHERE exit_time >= date_trunc('day', now())""")
            ).scalar_one()
            if loss_limit > 0 and today <= -loss_limit:
                conditions["daily_loss_limit"] = {
                    "severity": "critical", "title": "Today's loss limit was reached",
                    "message": f"Today is {today:.2f} USDT. New trades are paused until tomorrow (UTC).",
                    "details": {"today_pnl_usd": str(today), "limit_usd": str(loss_limit)}}
            unprotected = connection.execute(
                text("""SELECT count(*) FROM paper_positions WHERE status='open' AND stop_order_id IS NULL""")
            ).scalar_one()
            if unprotected and mode == "live":
                conditions["unprotected_positions"] = {
                    "severity": "critical", "title": "A lot has no stop order on Binance",
                    "message": f"{unprotected} open lot(s) are not protected by a stop order on Binance. The bot "
                               "still sells at its own stop, but a crash while it is offline would not be covered.",
                    "details": {"positions": unprotected}}
            # BNB pays Binance's fees, so its warnings only matter once a Binance account is attached.
            attached = credentials.attached()
            # In shadow mode with a starting amount the snapshot is the pretend wallet (no BNB), not Binance's.
            real_wallet = attached and not (mode != "live" and Decimal(str(settings.get("shadow_start_usd") or "0")) > 0)
            fee_market = markets.get(self.fee_symbol)
            fee_age = (now - fee_market["latest_open"]).total_seconds() if fee_market else None
            if attached and (fee_age is None or fee_age > self.stale_after_seconds):
                conditions["bnb_price_stale"] = {
                    "severity": "warning", "title": "BNB price is stale",
                    "message": "Without a fresh BNB price, fees are paid in USDT at the standard 0.10%.",
                    "details": {"age_seconds": fee_age}}
            trips_left = None
            lot_size = read_pot(connection).lot_size_usd
            round_trip = bnb_round_trip_usd(self.strategy, lot_size)
            if account and account["bnb_value_usd"] and round_trip:
                trips_left = int(account["bnb_value_usd"] / round_trip)
            if real_wallet and account is not None and account["bnb_free"] <= 0:
                conditions["bnb_empty"] = {
                    "severity": "warning", "title": "No BNB for fees",
                    "message": "Fees are being charged in USDT at 0.10% instead of 0.075%. Buy a little BNB on "
                               "Binance to get the discount.",
                    "details": {}}
            elif real_wallet and trips_left is not None and trips_left < LOW_BNB_ROUND_TRIPS:
                conditions["bnb_low"] = {
                    "severity": "warning", "title": "BNB is running low",
                    "message": f"BNB covers about {trips_left} more buy+sell at your lot size. Top it up on Binance.",
                    "details": {"round_trips_left": trips_left}}

            # Straight after a start the worker is downloading the minutes it missed, so prices look old and the
            # bot looks behind although nothing is wrong. Show one calm "catching up" notice instead of red alarms,
            # for a few minutes only: a real outage after that still raises every alert.
            if self.started_at and now - self.started_at < STARTUP_GRACE:
                catching_up = [key for key in conditions
                               if key.startswith(("market_data_stale", "market_data_gap"))
                               or key in ("execution_lag", "bnb_price_stale")]
                for key in catching_up:
                    conditions.pop(key)
                if catching_up:
                    conditions["starting_up"] = {
                        "severity": "warning", "title": "The bot is starting up",
                        "message": "It is catching up on the latest prices (after a first start or a restart). "
                                   "Trading starts on its own within a few minutes.",
                        "details": {"started_at": self.started_at.isoformat()}}
            existing = {
                row["alert_key"]: row["status"] for row in connection.execute(
                    text("SELECT alert_key, status FROM monitoring_alerts FOR UPDATE")
                ).mappings().all()
            }
            activated = resolved = 0
            for key, alert in conditions.items():
                if existing.get(key) != "active":
                    activated += 1
                    self._event(connection, "WARNING" if alert["severity"] == "warning" else "ERROR",
                                "alert_activated", {"alert_key": key, "title": alert["title"]})
                connection.execute(
                    text(
                        """
                        INSERT INTO monitoring_alerts (alert_key, severity, status, title, message, details,
                            first_seen_at, last_seen_at, resolved_at)
                        VALUES (:key, :severity, 'active', :title, :message, CAST(:details AS jsonb), now(), now(), NULL)
                        ON CONFLICT (alert_key) DO UPDATE SET
                            severity=EXCLUDED.severity, status='active', title=EXCLUDED.title,
                            message=EXCLUDED.message, details=EXCLUDED.details,
                            first_seen_at=CASE WHEN monitoring_alerts.status='resolved' THEN now()
                                               ELSE monitoring_alerts.first_seen_at END,
                            last_seen_at=now(), resolved_at=NULL
                        """
                    ),
                    {"key": key, "severity": alert["severity"], "title": alert["title"],
                     "message": alert["message"], "details": json.dumps(alert["details"], default=str)},
                )
            for key, status in existing.items():
                if key.startswith(MANAGED) and status == "active" and key not in conditions:
                    connection.execute(
                        text("UPDATE monitoring_alerts SET status='resolved', resolved_at=now(), last_seen_at=now() WHERE alert_key=:key"),
                        {"key": key},
                    )
                    resolved += 1
                    self._event(connection, "INFO", "alert_resolved", {"alert_key": key})
            critical = [key for key, alert in conditions.items() if alert["severity"] == "critical"]
            state = {
                "status": "healthy" if not conditions else ("attention" if critical else "warning"),
                "checked_at": now.isoformat(), "active_alerts": len(conditions),
                "activated_this_check": activated, "resolved_this_check": resolved,
                "execution_lag_minutes": lag, "behind_since": behind_since,
                "coins": {symbol: {"age_seconds": health["age_seconds"], "missing_candles": health["missing_candles"]}
                          for symbol, health in coin_health.items()},
                "bnb": {"age_seconds": round(fee_age, 1) if fee_age is not None else None,
                        "round_trips_left": trips_left},
            }
            connection.execute(
                text(
                    """
                    INSERT INTO engine_state (key, value, updated_at) VALUES ('monitoring', CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()
                    """
                ),
                {"value": json.dumps(state)},
            )
        return state

    @staticmethod
    def _event(connection, level: str, event_type: str, details: dict) -> None:
        connection.execute(
            text(
                """
                INSERT INTO system_events (level, component, event_type, details)
                VALUES (:level, 'monitoring', :event_type, CAST(:details AS jsonb))
                """
            ),
            {"level": level, "event_type": event_type, "details": json.dumps(details, default=str)},
        )
