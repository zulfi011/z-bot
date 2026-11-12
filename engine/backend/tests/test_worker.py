import logging
from unittest.mock import MagicMock

from app.worker import sync_account


def test_account_failure_still_runs_health_checks_and_keeps_the_worker_alive():
    execution, monitoring = MagicMock(), MagicMock()
    execution.synchronize.side_effect = RuntimeError("Recovery validation failed: example")
    assert sync_account(execution, monitoring, logging.getLogger("test")) is None
    monitoring.synchronize.assert_called_once()


def test_healthy_account_returns_its_status():
    execution, monitoring = MagicMock(), MagicMock()
    execution.synchronize.return_value = {"open_positions": 0, "account": None}
    assert sync_account(execution, monitoring, logging.getLogger("test")) == {"open_positions": 0, "account": None}
    monitoring.synchronize.assert_called_once()


def test_health_checks_are_not_repeated_for_every_candle():
    """Six feeds deliver a candle a minute; the full scan should not run six times."""
    execution, monitoring = MagicMock(), MagicMock()
    execution.synchronize.return_value = {"open_positions": 0}
    health = {"checked_at": 0.0}
    for _ in range(6):
        sync_account(execution, monitoring, logging.getLogger("test"), "SOLUSDT", health=health)
    assert monitoring.synchronize.call_count == 1
    assert execution.synchronize.call_count == 6   # trading still advances on every candle


def test_a_trading_failure_always_runs_the_health_checks_at_once():
    execution, monitoring = MagicMock(), MagicMock()
    execution.synchronize.side_effect = RuntimeError("boom")
    health = {"checked_at": 0.0}
    sync_account(execution, monitoring, logging.getLogger("test"), "SOLUSDT", health=health)  # arms the timer
    monitoring.synchronize.reset_mock()
    sync_account(execution, monitoring, logging.getLogger("test"), "SOLUSDT", health=health)
    monitoring.synchronize.assert_called_once()
