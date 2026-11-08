from datetime import datetime, timedelta, timezone

from app.domain.signal_engine import build_signal_engine
from app.services.signal_repository import SignalRepository


def next_signal_boundary(now: datetime, timeframe_minutes: int) -> datetime:
    minute = now.replace(second=0, microsecond=0)
    return minute - timedelta(minutes=minute.minute % timeframe_minutes) + timedelta(minutes=timeframe_minutes)


class SignalService:
    def __init__(self, repository: SignalRepository, strategy: dict) -> None:
        self.repository = repository
        self.strategy = strategy
        self.strategy_id = strategy["strategy_id"]
        self.symbol = strategy["market"]["symbol"]
        self.timeframe_minutes = int(strategy["market"]["signal_timeframe"].removesuffix("m"))
        self.signal_average_days = int(strategy["averages"]["signal_average_days"])

    def synchronize(self, recalculate_averages: bool = False) -> dict:
        """Rebuild signal state from persisted candles; persist only post-activation transitions.

        `recalculate_averages` is for callers that have just changed stored history (a backfill or a gap repair);
        otherwise the daily averages are left alone, because they only move at UTC midnight.
        """
        self.repository.refresh_daily_averages(self.symbol, self.signal_average_days, force=recalculate_averages)
        activation = self.repository.ensure_activation(
            self.strategy_id, next_signal_boundary(datetime.now(timezone.utc), self.timeframe_minutes)
        )
        candles = self.repository.load_signal_candles(self.symbol, self.timeframe_minutes)
        engine = build_signal_engine(self.strategy)
        live_transitions = 0
        details = {"timeframe": f"{self.timeframe_minutes}m", "signal_average_days": self.signal_average_days}
        for candle in candles:
            transition = engine.process(candle)
            if candle.open_time >= activation and (transition.episode or transition.resolution):
                self.repository.persist_transition(self.strategy_id, self.symbol, transition, details)
                live_transitions += 1

        latest = candles[-1] if candles else None
        status = {
            "status": "ready" if latest and latest.average_30d is not None and latest.signal_average is not None else "warming_up",
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe": f"{self.timeframe_minutes}m",
            "activation_at": activation.isoformat(),
            "latest_processed_candle": latest.open_time.isoformat() if latest else None,
            "latest_signal_average": str(latest.signal_average) if latest and latest.signal_average else None,
            "latest_regime": engine.regime(latest) if latest else None,
            "candles_replayed": len(candles),
            "episodes_seen_in_replay": engine.episodes_seen,
            "live_transitions_reconciled": live_transitions,
            "pending_episode": engine.pending.episode_id if engine.pending else None,
            "pending_since": engine.pending.start_time.isoformat() if engine.pending else None,
        }
        self.repository.record_status(self.symbol, status)
        return status
