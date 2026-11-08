import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.domain.market_data import Candle


class CandleRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def last_open_time(self, symbol: str) -> datetime | None:
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT max(open_time) FROM candles_1m WHERE symbol = :symbol"),
                {"symbol": symbol},
            ).scalar_one()

    def earliest_missing_open_time(self, symbol: str, through: datetime) -> datetime | None:
        with self.engine.connect() as connection:
            return connection.execute(
                text(
                    """
                    WITH bounds AS (
                        SELECT min(open_time) AS first_open_time
                        FROM candles_1m WHERE symbol = :symbol
                    ), expected AS (
                        SELECT generate_series(first_open_time, :through, interval '1 minute') AS open_time
                        FROM bounds WHERE first_open_time IS NOT NULL
                    )
                    SELECT min(expected.open_time)
                    FROM expected
                    LEFT JOIN candles_1m AS candle
                      ON candle.symbol = :symbol AND candle.open_time = expected.open_time
                    WHERE candle.open_time IS NULL
                    """
                ),
                {"symbol": symbol, "through": through},
            ).scalar_one()

    def save(self, candle: Candle) -> bool:
        return self.save_many([candle]) > 0

    def save_many(self, candles: list[Candle]) -> int:
        if not candles:
            return 0
        statement = text(
            """
            INSERT INTO candles_1m (
                symbol, open_time, close_time, open, high, low, close, volume,
                quote_volume, trade_count, source, source_event_time
            ) VALUES (
                :symbol, :open_time, :close_time, :open, :high, :low, :close, :volume,
                :quote_volume, :trade_count, :source, :source_event_time
            )
            ON CONFLICT (symbol, open_time) DO NOTHING
            """
        )
        rows = [candle.__dict__ for candle in candles]
        with self.engine.begin() as connection:
            result = connection.execute(statement, rows)
        return result.rowcount

    def record_state(self, key: str, value: dict) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO engine_state (key, value, updated_at)
                    VALUES (:key, CAST(:value AS jsonb), now())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = now()
                    """
                ),
                {"key": key, "value": json.dumps(value)},
            )

    def record_event(self, level: str, event_type: str, details: dict) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO system_events (level, component, event_type, details)
                    VALUES (:level, 'market_data', :event_type, CAST(:details AS jsonb))
                    """
                ),
                {"level": level, "event_type": event_type, "details": json.dumps(details)},
            )
