"""Request ids, crashes that do not leak details, and no control endpoint without the key check."""

import inspect

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api_patch import patch_api
from app.main import app


def test_every_answer_has_a_request_id_and_keeps_the_callers_own():
    client = TestClient(app, base_url="http://localhost")
    assert len(client.get("/api/v1/health/live").headers["x-request-id"]) == 12
    assert client.get("/api/v1/health/live", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"
    assert client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id!"}).headers["x-request-id"] != "bad id!"


def test_a_crash_returns_only_the_request_id(monkeypatch):
    def boom():
        raise RuntimeError("secret detail /app/path")
    patch_api(monkeypatch, "get_settings", boom)
    response = TestClient(app, base_url="http://localhost", raise_server_exceptions=False).get(
        "/api/v1/health/live", headers={"X-Request-ID": "trace-me"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error (request_id=trace-me)"}
    assert response.headers["x-request-id"] == "trace-me"


def test_every_control_checks_the_key():
    """A new endpoint that changes something but forgets the key check fails here."""
    open_on_purpose = {"/api/v1/session"}                     # unlocking and locking the device itself
    for route in app.routes:
        if isinstance(route, APIRoute) and route.methods & {"POST", "PUT", "PATCH", "DELETE"} \
                and route.path not in open_on_purpose:
            assert "_authorize(" in inspect.getsource(route.endpoint), f"{route.path} does not check the control key"
