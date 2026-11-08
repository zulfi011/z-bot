from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api import routes


@pytest.fixture
def controls(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(strategy_edit_token="test-key"))
    engine = MagicMock()
    monkeypatch.setattr(routes, "get_engine", lambda: engine)
    return engine


def test_controls_reject_a_wrong_key_before_touching_the_database(controls):
    for call in (lambda: routes.close_position("p", "wrong"),
                 lambda: routes.set_trading_mode(routes.TradingModeRequest(mode="live"), "wrong"),
                 lambda: routes.buy_now("SOLUSDT", "wrong"),
                 lambda: routes.set_pot(routes.PotRequest(lot_size_usd=100, lots=3), "wrong"),
                 lambda: routes.set_trading("BTCUSDT", routes.TradingSwitchRequest(enabled=False, close_positions=True), "wrong")):
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 403
    controls.begin.assert_not_called()


def test_controls_are_open_without_a_server_key(monkeypatch):
    """No control key = the app only listens on this computer, so no lock."""
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(strategy_edit_token=""))
    routes._authorize(None, None)  # does not raise


@pytest.mark.parametrize("position,expected", [(None, 404), ({"status": "closed"}, "closed")])
def test_close_handles_missing_and_closed_positions(controls, position, expected):
    connection = controls.begin.return_value.__enter__.return_value
    connection.execute.return_value.mappings.return_value.one_or_none.return_value = position
    if expected == 404:
        with pytest.raises(HTTPException) as error:
            routes.close_position("p", "test-key")
        assert error.value.status_code == 404
    else:
        assert routes.close_position("p", "test-key")["status"] == "closed"


def test_pot_request_rejects_bad_shapes():
    with pytest.raises(ValueError):
        routes.PotRequest(lot_size_usd=100, lots=0)
    with pytest.raises(ValueError):
        routes.PotRequest(lot_size_usd="100.005", lots=1)
    with pytest.raises(ValueError):
        routes.PotRequest(lot_size_usd=100, lots=51)


def test_unknown_coins_are_refused(controls):
    with pytest.raises(HTTPException) as error:
        routes.buy_now("DOGEUSDT", "test-key")
    assert error.value.status_code == 404
    controls.begin.assert_not_called()


def test_trading_switch_rejects_unknown_coins_and_fields(controls):
    with pytest.raises(HTTPException) as error:
        routes.set_trading("DOGEUSDT", routes.TradingSwitchRequest(enabled=False), "test-key")
    assert error.value.status_code == 404
    with pytest.raises(ValueError):
        routes.TradingSwitchRequest(enabled=False, sell_everything=True)


# ---------------------------------------------------------------- the shared pot
def test_the_pot_is_saved_as_one_setting_for_every_coin(controls):
    import json
    connection = controls.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 2
    result = routes.set_pot(routes.PotRequest(lot_size_usd="120", lots=5), "test-key")
    assert result["status"] == "applied" and result["lots"] == 5 and result["open_lots"] == 2
    saved = [call.args[1] for call in connection.execute.call_args_list
             if len(call.args) > 1 and "engine_state" in str(call.args[0])]
    assert json.loads(saved[0]["value"]) == {"pot_lots": 5, "pot_lot_size_usd": "120", "pot_set_by_user": True}


def test_a_pot_lot_below_the_minimum_is_refused(controls):
    with pytest.raises(HTTPException) as error:
        routes.set_pot(routes.PotRequest(lot_size_usd="1", lots=3), "test-key")
    assert error.value.status_code == 422 and "A lot must be between" in error.value.detail


def test_switching_a_coin_off_applies_at_once_and_can_close_its_lots(controls, monkeypatch):
    connection = controls.begin.return_value.__enter__.return_value
    monkeypatch.setattr(routes, "read_allocation", lambda connection, symbol: object())
    connection.execute.return_value.scalars.return_value = ["position:a", "position:b"]
    result = routes.set_trading("ETHUSDT", routes.TradingSwitchRequest(enabled=False, close_positions=True), "test-key")
    assert result["status"] == "applied" and result["enabled"] is False and len(result["closes"]) == 2
    switched = [call.args[1] for call in connection.execute.call_args_list
                if len(call.args) > 1 and "SET trading_enabled" in str(call.args[0])]
    assert switched == [{"on": False, "symbol": "ETHUSDT"}]


def test_buy_now_is_refused_when_every_shared_lot_is_open(controls, monkeypatch):
    from decimal import Decimal
    from app.services.live_execution_service import SharedPot
    monkeypatch.setattr(routes, "read_trading_enabled", lambda connection, symbol: True)
    monkeypatch.setattr(routes, "read_pot", lambda connection: SharedPot(3, Decimal("100")))
    monkeypatch.setattr(routes, "open_lot_total", lambda connection: 3)
    connection = controls.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 0          # nothing waiting
    with pytest.raises(HTTPException) as error:
        routes.buy_now("SOLUSDT", "test-key")
    assert error.value.status_code == 409 and "All 3 shared lots are open" in error.value.detail


def test_the_pot_endpoint_answers_a_real_request(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(strategy_edit_token="test-key"))
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = 0
    monkeypatch.setattr(routes, "get_engine", lambda: engine)
    server = TestClient(app, base_url="http://localhost")
    reply = server.put("/api/v1/pot", json={"lot_size_usd": "100", "lots": 4}, headers={"X-Control-Key": "test-key"})
    assert reply.status_code == 202, reply.text
    assert reply.json()["lots"] == 4
