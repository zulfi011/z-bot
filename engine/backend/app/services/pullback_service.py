"""Turns pullback reclaims into ordinary signals, so the execution service only has to know where to put them.

A reclaim inside an uptrend writes the same two rows a dip touch writes - an episode and a signal - marked with
`kind: pullback` in their details, already confirmed with its entry minute. The execution service buys it into a
pullback lot, never a core one.

The rule needs a 24-hour line and a running count of minutes below it, so unlike the quiet-band breakout it is not recomputed from
scratch every minute: the line and the count live in `engine_state` and advance one stored minute at a time. When
that state is missing or too far behind the candles, it is warmed up again from stored candles - 20 spans of the
line, the same warm-up the parity check (`research/backtests/scripts/verify_pullback_parity.py`) proved exact.

Reclaims found while warming up are only written if they happened after the rule was first switched on, so the
first start does not flood the history with signals nothing could have bought.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.domain.pullback import PullbackConfig, PullbackState, Reclaim, replay, warmup_minutes

ONE_MINUTE = timedelta(minutes=1)


class PullbackService:
    def __init__(self, engine: Engine, strategy: dict) -> None:
        self.engine = engine
        self.strategy_id = strategy["strategy_id"]
        self.symbol = strategy["market"]["symbol"]
        self.config = PullbackConfig.from_strategy(strategy)

    @property
    def enabled(self) -> bool:
        return self.config is not None

    @property
    def state_key(self) -> str:
        return f"pullback:{self.symbol}"

    def synchronize(self) -> dict:
        if not self.config:
            return {"enabled": False}
        config = self.config
        with self.engine.begin() as connection:
            stored = connection.execute(
                text("SELECT value FROM engine_state WHERE key=:key FOR UPDATE"), {"key": self.state_key}
            ).scalar_one_or_none() or {}
            newest = connection.execute(
                text("SELECT max(open_time) FROM candles_1m WHERE symbol=:s"), {"s": self.symbol}
            ).scalar_one()
            if newest is None:
                return {"enabled": True, "symbol": self.symbol, "status": "waiting_for_candles"}
            if stored.get("strategy_id") not in (None, self.strategy_id):
                stored = {}                     # a new strategy version starts its own count
            # The rule is switched on at the newest stored minute; nothing before it is ever written.
            activation = datetime.fromisoformat(stored["activation_at"]) if stored.get("activation_at") else newest
            state = PullbackState.from_json(stored.get("state"))
            warmup = warmup_minutes(config)
            rewarmed = state.at is None or state.at < newest - timedelta(minutes=warmup)
            if rewarmed:
                state = PullbackState()
                rows = connection.execute(
                    text("""SELECT open_time, close FROM candles_1m
                            WHERE symbol=:s AND open_time > :newest - make_interval(mins => :warmup)
                            ORDER BY open_time"""),
                    {"s": self.symbol, "newest": newest, "warmup": warmup},
                ).all()
            else:
                rows = connection.execute(
                    text("""SELECT open_time, close FROM candles_1m WHERE symbol=:s AND open_time > :at
                            ORDER BY open_time"""),
                    {"s": self.symbol, "at": state.at},
                ).all()
            state, reclaims = replay(rows, config, state)

            written = confirmed = skipped = 0
            regimes: dict[datetime, str | None] = {}
            last = stored.get("last_reclaim")
            for reclaim in reclaims:
                regime = self._regime(connection, reclaim.reclaim_at, regimes)
                last = {"reclaim_at": reclaim.reclaim_at.isoformat(), "regime": regime,
                        "below_minutes": reclaim.below_minutes, "line": str(reclaim.line)}
                if reclaim.reclaim_at < activation or (config.requires_uptrend and regime != "bullish"):
                    continue                    # before switch-on, or a dip outside an uptrend: not a setup
                status = "skipped_time_window" if config.blocked(reclaim.entry_at) else "confirmed"
                if self._record(connection, reclaim, status):
                    written += 1
                    confirmed += status == "confirmed"
                    skipped += status == "skipped_time_window"

            value = {
                "enabled": True, "symbol": self.symbol, "strategy_id": self.strategy_id,
                "activation_at": activation.isoformat(), "state": state.to_json(),
                "ema_minutes": config.ema_minutes, "dwell_minutes": config.dwell_minutes,
                "line": None if state.ema is None else str(state.ema),
                "line_at": None if state.at is None else state.at.isoformat(),
                "below_since": None if state.below_since is None else state.below_since.isoformat(),
                "below_minutes": state.below_minutes, "last_reclaim": last,
                "minutes_read": len(rows), "rewarmed": rewarmed, "new_signals": written,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            connection.execute(
                text("""INSERT INTO engine_state (key, value, updated_at)
                        VALUES (:key, CAST(:value AS jsonb), now())
                        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()"""),
                {"key": self.state_key, "value": json.dumps(value)},
            )
        return {**value, "confirmed": confirmed, "skipped": skipped}

    def _regime(self, connection: Connection, at: datetime, cache: dict) -> str | None:
        """The trend for that UTC day, from the daily averages effective on it - the research's definition."""
        day = at.replace(hour=0, minute=0, second=0, microsecond=0)
        if day not in cache:
            row = connection.execute(
                text("""SELECT average_7d, average_15d, average_30d FROM daily_averages
                        WHERE symbol=:s AND effective_at=:day"""),
                {"s": self.symbol, "day": day},
            ).mappings().one_or_none()
            if not row or None in (row["average_7d"], row["average_15d"], row["average_30d"]):
                cache[day] = None
            else:
                a7, a15, a30 = row["average_7d"], row["average_15d"], row["average_30d"]
                cache[day] = "bullish" if a7 > a15 > a30 else "bearish" if a7 < a15 < a30 else "neutral"
        return cache[day]

    def _record(self, connection: Connection, reclaim: Reclaim, status: str) -> bool:
        details = json.dumps({
            "kind": "pullback", "below_since": reclaim.below_since.isoformat(),
            "below_minutes": reclaim.below_minutes, "line": str(reclaim.line), "close": str(reclaim.close),
            "ema_minutes": self.config.ema_minutes, "dwell_minutes": self.config.dwell_minutes,
            "blocked_hours": list(self.config.blocked_entry_hours) if self.config.blocked_entry_hours else None,
        })
        inserted = connection.execute(
            text("""INSERT INTO touch_episodes (episode_id, strategy_id, symbol, touch_time, average_value,
                                                status, details)
                    VALUES (:id, :strategy, :symbol, :at, :line, :status, CAST(:details AS jsonb))
                    ON CONFLICT (episode_id) DO NOTHING"""),
            {"id": reclaim.pullback_id, "strategy": self.strategy_id, "symbol": self.symbol,
             "at": reclaim.reclaim_at, "line": reclaim.line, "status": status, "details": details},
        ).rowcount
        if not inserted:
            return False
        connection.execute(
            text("""INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, status, entry_time,
                                         reason, details)
                    VALUES (:id, :id, :strategy, :at, :status, :entry, :reason, CAST(:details AS jsonb))
                    ON CONFLICT (signal_id) DO NOTHING"""),
            {"id": reclaim.pullback_id, "strategy": self.strategy_id, "at": reclaim.reclaim_at, "status": status,
             "entry": reclaim.entry_at if status == "confirmed" else None,
             "reason": "blocked entry hours" if status == "skipped_time_window" else None, "details": details},
        )
        return True
