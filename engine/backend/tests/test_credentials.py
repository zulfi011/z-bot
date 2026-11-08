"""Attaching a Binance key from the dashboard: where it is kept, what is refused, and the Live guard."""

import os
import stat
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import routes
from app.core import credentials
from app.services.binance_client import BinanceClient, BinanceError

KEY, SECRET = "A" * 64, "B" * 64


@pytest.fixture
def store(tmp_path, monkeypatch):
    settings = SimpleNamespace(binance_credentials_path=tmp_path / "secrets" / "binance.json",
                               binance_api_key="", binance_api_secret="", strategy_edit_token="",
                               binance_api_url="http://binance.test", binance_recv_window_ms=5000)
    monkeypatch.setattr(credentials, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(credentials, "_cache", None)
    return settings


def test_saved_key_is_owner_only_and_never_echoed(store):
    credentials.save(f" {KEY} ", SECRET)
    path = store.binance_credentials_path
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert credentials.current() == (KEY, SECRET) and credentials.source() == "dashboard"
    view = routes.credentials_status()
    assert view == {"attached": True, "source": "dashboard", "key_hint": "AAAA…AAAA"}
    assert SECRET not in str(view)
    credentials.remove()
    assert credentials.current() is None and routes.credentials_status()["attached"] is False


def test_dashboard_key_wins_over_environment_key(store):
    store.binance_api_key, store.binance_api_secret = "E" * 64, "F" * 64
    assert credentials.source() == "environment"
    credentials.save(KEY, SECRET)
    assert credentials.current() == (KEY, SECRET)


def test_client_picks_up_a_newly_attached_key_without_restart(store):
    client = BinanceClient("", "", credentials=credentials.from_file)
    assert not client.configured
    credentials.save(KEY, SECRET)
    assert client.configured and client._key == KEY


def answers(account=None, restrictions=None, error=None):
    def signed_get(self, path, params=None):
        if error:
            raise error
        return account if path == "/api/v3/account" else restrictions
    return signed_get


def test_key_that_can_withdraw_is_refused(store, monkeypatch):
    monkeypatch.setattr(BinanceClient, "signed_get",
                        answers({"canTrade": True}, {"enableWithdrawals": True, "enableSpotAndMarginTrading": True}))
    with pytest.raises(HTTPException) as error:
        routes.attach_credentials(routes.CredentialsRequest(api_key=KEY, api_secret=SECRET), None, None)
    assert error.value.status_code == 400 and "withdraw" in error.value.detail
    assert credentials.current() is None


def test_key_binance_rejects_is_not_saved(store, monkeypatch):
    monkeypatch.setattr(BinanceClient, "signed_get", answers(error=BinanceError(-2015, "Invalid API-key")))
    with pytest.raises(HTTPException) as error:
        routes.attach_credentials(routes.CredentialsRequest(api_key=KEY, api_secret=SECRET), None, None)
    assert error.value.status_code == 400 and credentials.current() is None


def test_good_key_is_attached(store, monkeypatch):
    monkeypatch.setattr(BinanceClient, "signed_get",
                        answers({"canTrade": True}, {"enableWithdrawals": False, "enableSpotAndMarginTrading": True}))
    view = routes.attach_credentials(routes.CredentialsRequest(api_key=KEY, api_secret=SECRET), None, None)
    assert view["attached"] is True and credentials.current() == (KEY, SECRET)


def test_live_needs_an_attached_key(store):
    with pytest.raises(HTTPException) as error:
        routes.set_trading_mode(routes.TradingModeRequest(mode="live"), None, None)
    assert error.value.status_code == 409 and "Attach" in error.value.detail


def test_badly_formatted_key_is_refused_without_echoing_it(store):
    with pytest.raises(HTTPException) as error:
        routes.attach_credentials(routes.CredentialsRequest(api_key="short", api_secret="TOP-SECRET-VALUE"), None, None)
    assert error.value.status_code == 400 and "TOP-SECRET-VALUE" not in error.value.detail
