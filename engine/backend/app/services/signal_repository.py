import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.signal_engine import SignalCandle, SignalTransition


class SignalRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def daily_averages_are_current(self, symbol: str, signal_days: int) -> bool:
        """Is today's row already there? Averages only change when a UTC day completes."""
        with self.engine.connect() as connection:
            stored = connection.execute(
                text("""SELECT signal_average_days FROM daily_averages
                        WHERE symbol=:symbol AND effective_at=date_trunc('day', now())"""),
                {"symbol": symbol},
            ).scalar_one_or_none()
        return stored is not None and int(stored) == int(signal_days)

    def refresh_daily_averages(self, symbol: str, signal_days: int, force: bool = False) -> None:
        """Completed UTC days only; each average needs exactly `period` days and
        becomes effective at the next UTC midnight.

        This reads every stored candle for the coin, so it is skipped when today's averages are already there:
        they cannot change until the next UTC midnight. `force` is for the paths that change history — the
        startup backfill and a gap repair — where stored days really can have changed.
        """
        days = int(signal_days)
        if not force and self.daily_averages_are_current(symbol, days):
            return
        statement = text(
            f"""
            WITH complete_daily AS (
                SELECT date_trunc('day', open_time) AS day,
                       (array_agg(close ORDER BY open_time DESC))[1] AS close
                FROM candles_1m
                WHERE symbol = :symbol AND open_time < date_trunc('day', now())
                GROUP BY 1
                HAVING count(*) = 1440
            ), rolling AS (
                SELECT day,
                       count(close) OVER w7 AS count_7, avg(close) OVER w7 AS average_7d,
                       count(close) OVER w15 AS count_15, avg(close) OVER w15 AS average_15d,
                       count(close) OVER w30 AS count_30, avg(close) OVER w30 AS average_30d,
                       count(close) OVER wn AS count_n, avg(close) OVER wn AS average_n
                FROM complete_daily
                WINDOW w7 AS (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
                       w15 AS (ORDER BY day ROWS BETWEEN 14 PRECEDING AND CURRENT ROW),
                       w30 AS (ORDER BY day ROWS BETWEEN 29 PRECEDING AND CURRENT ROW),
                       wn AS (ORDER BY day ROWS BETWEEN {days - 1} PRECEDING AND CURRENT ROW)
            )
            INSERT INTO daily_averages (
                symbol, effective_at, completed_through, average_7d, average_15d, average_30d,
                signal_average_days, signal_average
            )
            SELECT :symbol, day + interval '1 day', day::date,
                   CASE WHEN count_7 = 7 THEN average_7d END,
                   CASE WHEN count_15 = 15 THEN average_15d END,
                   CASE WHEN count_30 = 30 THEN average_30d END,
                   {days},
                   CASE WHEN count_n = {days} THEN average_n END
            FROM rolling
            ON CONFLICT (symbol, effective_at) DO UPDATE SET
                completed_through = EXCLUDED.completed_through,
                average_7d = EXCLUDED.average_7d,
                average_15d = EXCLUDED.average_15d,
                average_30d = EXCLUDED.average_30d,
                signal_average_days = EXCLUDED.signal_average_days,
                signal_average = EXCLUDED.signal_average,
                calculated_at = now()
            """
        )
        with self.engine.begin() as connection:
            connection.execute(statement, {"symbol": symbol})

    def load_signal_candles(self, symbol: str, timeframe_minutes: int) -> list[SignalCandle]:
        if timeframe_minutes not in {1, 3, 5}:
            raise ValueError("Unsupported signal timeframe")
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    WITH grouped AS (
                        SELECT date_bin(make_interval(mins => :minutes), open_time, TIMESTAMPTZ '1970-01-01') AS open_time,
                               (array_agg(open ORDER BY open_time))[1] AS open,
                               max(high) AS high, min(low) AS low,
                               (array_agg(close ORDER BY open_time DESC))[1] AS close,
                               min(open_time) AS first_minute, max(open_time) AS last_minute,
                               count(*) AS minute_count
                        FROM candles_1m WHERE symbol=:symbol GROUP BY 1
                    )
                    SELECT grouped.open_time, grouped.open, grouped.high, grouped.low, grouped.close,
                           averages.signal_average, averages.average_7d,
                           averages.average_15d, averages.average_30d
                    FROM grouped
                    LEFT JOIN daily_averages AS averages
                      ON averages.symbol=:symbol
                     AND averages.effective_at=date_trunc('day', grouped.open_time)
                    WHERE grouped.minute_count=:minutes
                      AND grouped.first_minute=grouped.open_time
                      AND grouped.last_minute=grouped.open_time + make_interval(mins => (:minutes - 1))
                    ORDER BY grouped.open_time
                    """
                ),
                {"symbol": symbol, "minutes": timeframe_minutes},
            ).mappings().all()
        return [SignalCandle(**dict(row)) for row in rows]

    def ensure_activation(self, strategy_id: str, activation_at: datetime) -> datetime:
        state_key = f"signal_engine_activation:{strategy_id}"
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO engine_state (key, value, updated_at)
                    VALUES (:key, CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO NOTHING
                    """
                ),
                {"key": state_key, "value": json.dumps({"activation_at": activation_at.isoformat()})},
            )
            value = connection.execute(
                text("SELECT value->>'activation_at' FROM engine_state WHERE key = :key"),
                {"key": state_key},
            ).scalar_one()
        return datetime.fromisoformat(value)

    def persist_transition(self, strategy_id: str, symbol: str, transition: SignalTransition,
                           details: dict) -> None:
        with self.engine.begin() as connection:
            if transition.episode is not None:
                episode = transition.episode
                episode_details = {**details, "regime": episode.regime, "from_below": episode.from_below}
                connection.execute(
                    text(
                        """
                        INSERT INTO touch_episodes (
                            episode_id, strategy_id, symbol, touch_time, average_value, status, details
                        ) VALUES (
                            :episode_id, :strategy_id, :symbol, :touch_time, :average_value,
                            :status, CAST(:details AS jsonb)
                        ) ON CONFLICT (episode_id) DO NOTHING
                        """
                    ),
                    {
                        "episode_id": episode.episode_id, "strategy_id": strategy_id, "symbol": symbol,
                        "touch_time": episode.touch_time, "average_value": episode.average_value,
                        "status": episode.status, "details": json.dumps(episode_details),
                    },
                )
                if episode.status == "pending_confirmation":
                    connection.execute(
                        text(
                            """
                            INSERT INTO signals (signal_id, episode_id, strategy_id, signal_time, status, details)
                            VALUES (:signal_id, :episode_id, :strategy_id, :signal_time,
                                    'pending_confirmation', CAST(:details AS jsonb))
                            ON CONFLICT (signal_id) DO NOTHING
                            """
                        ),
                        {
                            "signal_id": episode.episode_id, "episode_id": episode.episode_id,
                            "strategy_id": strategy_id, "signal_time": episode.touch_time,
                            "details": json.dumps(episode_details),
                        },
                    )

            if transition.resolution is not None:
                resolution = transition.resolution
                resolution_details = {
                    "confirmation_time": resolution.confirmation_time.isoformat()
                    if resolution.confirmation_time else None,
                    "confirmation_close": str(resolution.confirmation_close)
                    if resolution.confirmation_close is not None else None,
                }
                connection.execute(
                    text("UPDATE touch_episodes SET status = :status WHERE episode_id = :episode_id"),
                    {"status": resolution.status, "episode_id": resolution.episode_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE signals SET
                            signal_time = COALESCE(:confirmation_time, signal_time),
                            entry_time = :entry_time,
                            status = CASE WHEN signals.status LIKE 'ignored%' THEN signals.status ELSE :status END,
                            reason = CASE WHEN signals.status LIKE 'ignored%' THEN signals.reason ELSE :reason END,
                            details = signals.details || CAST(:details AS jsonb)
                        WHERE signal_id = :signal_id
                        """
                    ),
                    {
                        "signal_id": resolution.episode_id,
                        "confirmation_time": resolution.confirmation_time,
                        "entry_time": resolution.entry_time,
                        "status": resolution.status,
                        "reason": None if resolution.status == "confirmed" else resolution.status,
                        "details": json.dumps(resolution_details),
                    },
                )

    def record_status(self, symbol: str, value: dict) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO engine_state (key, value, updated_at)
                    VALUES (:key, CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                    """
                ),
                {"key": f"signal_engine:{symbol}", "value": json.dumps(value)},
            )
