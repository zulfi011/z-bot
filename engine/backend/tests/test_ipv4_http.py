"""Binance's key whitelist is IPv4-only, so the signed calls must never leave over IPv6."""

import socket
from urllib.request import Request

import pytest

from app.services import binance_client as client_module
from app.services import binance_reachability as reachability
from app.services.ipv4_http import IPv4HTTPSConnection, connect_ipv4


def test_only_ipv4_addresses_are_resolved(monkeypatch):
    asked = {}

    def fake_getaddrinfo(host, port, family=0, *args, **kwargs):
        asked["family"] = family
        return []

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(OSError, match="no IPv4 address"):
        connect_ipv4(("api.binance.com", 443), timeout=1)
    assert asked["family"] == socket.AF_INET


def test_the_https_connection_uses_the_ipv4_dialer():
    assert IPv4HTTPSConnection._create_connection is connect_ipv4


def test_binance_calls_and_the_reachability_probe_use_the_ipv4_opener(monkeypatch):
    for module in (client_module, reachability):
        assert module.urlopen_ipv4.__module__ == "app.services.ipv4_http"
    calls = []
    monkeypatch.setattr(client_module, "urlopen_ipv4", lambda request, timeout: calls.append(request) or _Empty())
    client_module.BinanceClient("key", "secret")._request("GET", "/api/v3/time")
    assert calls and calls[0].full_url.endswith("/api/v3/time")


class _Empty:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b"null"
