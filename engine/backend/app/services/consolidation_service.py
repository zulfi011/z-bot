"""Turns quiet-band breakouts into ordinary signals, so the rest of the bot needs to know nothing new.

A consolidation break writes the same two rows a dip touch writes - an episode and a signal - marked with
`kind: consolidation` in their details. From there the normal machinery takes over: the execution service buys
any confirmed signal whose entry minute has arrived, and the dashboard lists it beside the dip signals.

Everything is recomputed from stored candles on each pass and written with upserts, so a restart, a backfill
or a repeated run all land on the same rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.consolidation import ConsolidationConfig, build_bars, confirm, current_zone, find_breakouts

# How much history each pass reads. Enough for the zone, the wait and a few spare bars, so a break that
# happened while the bot was down is still found when it comes back.
LOOKBACK_BARS = 4


class _Candle:
    __slots__ = ("open_time", "high", "low", "close")

    def __init__(self, open_time: datetime, high: Decimal, low: Decimal, close: Decimal) -> None:
        self.open_time, self.high, self.low, self.close = open_time, high, low, close


class ConsolidationService:
    def __init__(self, engine: Engine, strategy: dict) -> None:
        self.engine = engine
        self.strategy_id = strategy["strategy_id"]
        self.symbol = strategy["market"]["symbol"]
        self.config = ConsolidationConfig.from_strategy(strategy)

    @property
    def enabled(self) -> bool:
        return self.config is not None

    def synchronize(self) -> dict:
        """Find breaks, resolve the ones whose wait has run out, and report what the zone looks like now."""
        if not self.config:
            return {"enabled": False}
        config = self.config
        minutes = config.chart_minutes * (config.zone_bars + LOOKBACK_BARS) + config.confirmation_wait_minutes
        with self.engine.begin() as connection:
            rows = connection.execute(
                # Anchored on the newest stored candle, not the clock: after an outage the bot backfills the
                # minutes it missed, and a window measured from "now" would skip straight past them.
                text("""SELECT open_time, high, low, close FROM candles_1m
                        WHERE symbol=:symbol AND open_time >= (
                                  SELECT max(open_time) FROM candles_1m WHERE symbol=:symbol
                              ) - make_interval(mins => :minutes)
                        ORDER BY open_time"""),
                {"symbol": self.symbol, "minutes": minutes},
            ).all()
            candles = [_Candle(*row) for row in rows]
            closes = {candle.open_time: candle.close for candle in candles}
            bars = build_bars(candles, config.chart_minutes)
            zone, quiet = current_zone(bars, config)
            breakouts = find_breakouts(bars, config)

            found = confirmed = failed = 0
            for breakout in breakouts:
                if config.blocked(breakout.confirm_at + timedelta(minutes=1)):
                    continue
                found += self._remember(connection, breakout)
                state, entry_at = confirm(breakout, closes)
                if state == "confirmed":
                    confirmed += self._resolve(connection, breakout, "confirmed", entry_at)
                elif state == "failed":
                    failed += self._resolve(connection, breakout, "expired", None)

            status = {
                "enabled": True, "symbol": self.symbol, "bars": len(bars),
                "chart_minutes": config.chart_minutes, "zone_bars": config.zone_bars,
                "quiet": quiet,
                "zone_top": str(zone.top) if zone else None,
                "zone_bottom": str(zone.bottom) if zone else None,
                "zone_width_pct": str(round(zone.width_pct, 4)) if zone else None,
                "maximum_zone_pct": str(config.maximum_zone_pct),
                "zone_since": zone.since.isoformat() if zone else None,
                "breakouts_seen": len(breakouts), "new": found, "confirmed": confirmed, "expired": failed,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            connection.execute(
                text("""INSERT INTO engine_state (key, value, updated_at)
                        VALUES (:key, CAST(:value AS jsonb), now())
                        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()"""),
                {"key": f"consolidation:{self.symbol}", "value": json.dumps(status)},
            )
        return status

    def _remember(self, connection, breakout) -> int:
        details = json.dumps({
            "kind": "consolidation", "zone_top": str(breakout.zone.top), "zone_bottom": str(breakout.zone.bottom),
            "zone_width_pct": str(round(breakout.zone.width_pct, 4)), "zone_bars": breakout.zone.bars,
            "zone_since": breakout.zone.since.isoformat(), "breakout_close": str(breakout.close),
            "confirm_at": breakout.confirm_at.isoformat(),
        })
        inserted = connection.execute(
            text("""INSERT INTO touch_episodes (episode_id, strategy_id, symbol, touch_time, average_value,
                                                status, details)
                    VALUES (:id, :strategy, :symbol, :at, :top, 'pending_confirmation', CAST(:details AS jsonb))
                    ON CONFLICT (episode_id) DO NOTHING"""),
            {"id": breakout.breakout_id, "strategy": self.strategy_id, "symbol": self.symbol,
             "at": breakout.broke_at, "top": breakout.zone.top, "details": details},
        ).rowcount
        connection.execute(
            text("""INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, status, details)
                    VALUES (:id, :id, :strategy, :at, 'pending_confirmation', CAST(:details AS jsonb))
                    ON CONFLICT (signal_id) DO NOTHING"""),
            {"id": breakout.breakout_id, "strategy": self.strategy_id, "at": breakout.broke_at,
             "details": details},
        )
        return int(inserted or 0)

    def _resolve(self, connection, breakout, status: str, entry_at: datetime | None) -> int:
        """Settle a break once its wait has run out. Never touches a signal that already bought."""
        reason = "price fell back into the zone during the wait" if status == "expired" else None
        changed = connection.execute(
            text("""UPDATE signals SET status=:status, entry_time=:entry, reason=:reason
                    WHERE signal_id=:id AND status='pending_confirmation'"""),
            {"id": breakout.breakout_id, "status": status, "entry": entry_at, "reason": reason},
        ).rowcount
        connection.execute(
            text("UPDATE touch_episodes SET status=:status WHERE episode_id=:id AND status='pending_confirmation'"),
            {"id": breakout.breakout_id, "status": status},
        )
        return int(changed or 0)
