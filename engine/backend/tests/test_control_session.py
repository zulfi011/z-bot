"""Unlock once per device: a signed cookie instead of the key in every request."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import common
from api_patch import patch_api
from app.core import control_session as session

KEY = "the-real-control-key"


def test_a_session_is_valid_until_it_expires():
    token, expires = session.issue(KEY, now=1_000)
    assert session.expiry(token, KEY, now=1_000) == expires
    assert session.expiry(token, KEY, now=expires + 1) is None


def test_a_forged_or_edited_cookie_is_refused():
    token, expires = session.issue(KEY, now=1_000)
    later = str(expires + 10_000_000)
    assert session.expiry(f"{later}.{token.split('.')[1]}", KEY, now=1_000) is None  # pushed the expiry out
    assert session.expiry(token[:-1] + ("0" if token[-1] != "0" else "1"), KEY, now=1_000) is None
    assert session.expiry("garbage", KEY) is None and session.expiry(None, KEY) is None


def test_changing_the_key_on_the_server_locks_every_device():
    token, _ = session.issue(KEY, now=1_000)
    assert session.expiry(token, "a-new-key", now=1_000) is None


def test_guessing_the_key_is_slowed_down():
    session.clear_failures("1.2.3.4")
    for _ in range(session.FAILURE_LIMIT):
        assert session.blocked_for("1.2.3.4", now=100) == 0
        session.record_failure("1.2.3.4", now=100)
    assert session.blocked_for("1.2.3.4", now=100) > 0
    assert session.blocked_for("1.2.3.4", now=100 + session.FAILURE_WINDOW + 1) == 0   # the wait ends
    assert session.blocked_for("5.6.7.8", now=100) == 0                                 # others are unaffected


@pytest.fixture
def server(monkeypatch):
    patch_api(monkeypatch, "get_settings", lambda: SimpleNamespace(strategy_edit_token=KEY))
    session._failures.clear()
    from app.main import app
    return TestClient(app, base_url="http://localhost")


def test_unlock_act_and_lock_through_the_api(server, monkeypatch):
    assert server.get("/api/v1/session").json()["unlocked"] is False
    assert server.post("/api/v1/session", json={"key": "wrong"}).status_code == 403

    unlocked = server.post("/api/v1/session", json={"key": KEY})
    assert unlocked.status_code == 200
    cookie = unlocked.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    assert KEY not in unlocked.headers["set-cookie"]                    # the key itself never goes to the browser
    assert server.get("/api/v1/session").json()["unlocked"] is True

    # An unlocked device passes the control check with no key at all.
    token = server.cookies.get(session.COOKIE)
    common._authorize(None, token)

    server.delete("/api/v1/session")
    assert server.get("/api/v1/session").json()["unlocked"] is False


def test_a_locked_device_is_refused_with_a_clear_message(monkeypatch):
    patch_api(monkeypatch, "get_settings", lambda: SimpleNamespace(strategy_edit_token=KEY))
    with pytest.raises(HTTPException) as error:
        common._authorize(None, None)
    assert error.value.status_code == 403 and "locked" in error.value.detail
    common._authorize(KEY, None)                                        # scripts may still send the key header


def test_the_key_can_be_guessed_only_a_few_times(server):
    for _ in range(session.FAILURE_LIMIT):
        assert server.post("/api/v1/session", json={"key": "nope"}).status_code == 403
    blocked = server.post("/api/v1/session", json={"key": KEY})
    assert blocked.status_code == 429                                   # even the right key waits out the lockout
