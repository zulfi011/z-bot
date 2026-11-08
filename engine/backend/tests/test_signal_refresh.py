"""Daily averages move at UTC midnight, so they must not be recomputed on every candle."""

from unittest.mock import MagicMock

from app.services.signal_repository import SignalRepository
from app.services.signal_service import SignalService


def repository(current: bool) -> SignalRepository:
    repo = SignalRepository(MagicMock())
    repo.daily_averages_are_current = lambda symbol, days: current  # type: ignore[method-assign]
    return repo


def test_todays_averages_are_left_alone():
    repo = repository(current=True)
    repo.refresh_daily_averages("SOLUSDT", 12)
    repo.engine.begin.assert_not_called()


def test_a_missing_day_is_calculated():
    repo = repository(current=False)
    repo.refresh_daily_averages("SOLUSDT", 12)
    repo.engine.begin.assert_called_once()


def test_a_backfill_forces_a_recalculation_even_when_today_is_there():
    repo = repository(current=True)
    repo.refresh_daily_averages("SOLUSDT", 12, force=True)
    repo.engine.begin.assert_called_once()


def test_a_changed_signal_average_length_is_not_mistaken_for_current():
    repo = SignalRepository(MagicMock())
    connection = repo.engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one_or_none.return_value = 7   # stored for a 7-day average
    assert repo.daily_averages_are_current("SOLUSDT", 12) is False        # the strategy now wants 12
    assert repo.daily_averages_are_current("SOLUSDT", 7) is True


def test_the_signal_engine_only_recalculates_averages_when_asked():
    from app.core.strategy import load_strategies
    repo = MagicMock()
    repo.load_signal_candles.return_value = []
    service = SignalService(repo, load_strategies()["SOLUSDT"])
    service.synchronize()
    assert repo.refresh_daily_averages.call_args.kwargs == {"force": False}
    service.synchronize(recalculate_averages=True)
    assert repo.refresh_daily_averages.call_args.kwargs == {"force": True}
