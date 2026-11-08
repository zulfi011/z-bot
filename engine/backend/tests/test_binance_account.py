import hashlib
import hmac
from decimal import Decimal

import pytest

from app.services import binance_account
from app.services.binance_client import BinanceClient, BinanceError

# Example secret from Binance's public API documentation, not a real key (gitleaks:allow).
SECRET = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"


def client(monkeypatch, answers):
    binance_account._settings.clear()  # each test starts with nothing cached
    api = BinanceClient("key", SECRET)
    calls = []

    def fake(method, path, params=None, signed=False):
        calls.append((path, dict(params or {}), signed))
        if path == "/api/v3/time":
            return {"serverTime": 1700000000000}
        value = answers[path]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(api, "_request", fake)
    return api, calls


def test_signed_requests_carry_a_correct_signature(monkeypatch):
    api = BinanceClient("key", SECRET)
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["header"] = request.headers.get("X-mbx-apikey")

        class Response:
            status = 200
            def read(self): return b'{"serverTime": 1700000000000}'
            def __enter__(self): return self
            def __exit__(self, *args): return False
        return Response()

    monkeypatch.setattr("app.services.binance_client.urlopen_ipv4", fake_urlopen)
    api.signed_get("/api/v3/account", {"omitZeroBalances": "true"})
    query, signature = sent["url"].split("?", 1)[1].rsplit("&signature=", 1)
    assert signature == hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    assert sent["header"] == "key" and "recvWindow" in query and "timestamp" in query


def test_binance_errors_are_explained_in_plain_language():
    error = BinanceError(-2015, "Invalid API-key, IP, or permissions for action.")
    assert "IP restriction" in error.explanation
    assert BinanceError(-1013, "Filter failure").explanation.startswith("The order does not meet")


def test_account_snapshot_lists_balances_and_flags_dangerous_permissions(monkeypatch):
    answers = {
        "/api/v3/account": {"accountType": "SPOT", "canTrade": True, "balances": [
            {"asset": "USDT", "free": "250.5", "locked": "0"},
            {"asset": "BNB", "free": "0.02", "locked": "0"},
            {"asset": "ETH", "free": "0.04", "locked": "0"},
            {"asset": "DOGE", "free": "500", "locked": "0"}]},
        "/sapi/v1/account/apiRestrictions": {"ipRestrict": False, "enableReading": True,
                                             "enableSpotAndMarginTrading": True, "enableWithdrawals": True},
        "/sapi/v1/bnbBurn": {"spotBNBBurn": False},
        "/api/v3/account/commission": {"standardCommission": {"maker": "0.001", "taker": "0.001"},
                                       "discount": {"enabledForAccount": True, "discount": "0.75"}},
    }
    api, _ = client(monkeypatch, answers)
    prices = {"ETHUSDT": Decimal("2500"), "BNBUSDT": Decimal("600"), "DOGEUSDT": Decimal("0.1")}
    result = binance_account.snapshot(api, ["ETHUSDT"], prices, {"ETHUSDT": "Ethereum"}, force=True)
    assert result["connected"] and result["usdt"]["free"] == "250.5"
    assert result["coins"][0]["value_usdt"] == "100.00"
    assert result["bnb"]["value_usdt"] == "12.00"
    assert [a["asset"] for a in result["other_assets"]] == ["DOGE"]  # holdings the bot must never sell
    levels = {c["title"]: c["level"] for c in result["checks"]}
    assert levels["Withdrawals are enabled on this key"] == "danger"
    assert levels["The key is not locked to this server's IP"] == "warning"
    assert levels["BNB fee discount is off"] == "warning"
    assert result["coins"][0]["fees"]["taker_pct"] == pytest.approx(0.1)
    # Binance reports discount 0.75: you pay 75% of the fee, a 25% saving - not "75% off".
    assert result["coins"][0]["fees"]["bnb_discount_pct"] == pytest.approx(25)


def test_a_rejected_key_is_reported_not_raised(monkeypatch):
    answers = {"/api/v3/account": BinanceError(-2015, "Invalid API-key, IP, or permissions for action.")}
    api, _ = client(monkeypatch, answers)
    result = binance_account.snapshot(api, ["ETHUSDT"], {}, {}, force=True)
    assert result["connected"] is False and result["binance_code"] == -2015 and "IP restriction" in result["message"]


def test_without_a_key_the_dashboard_is_told_what_to_do():
    result = binance_account.snapshot(BinanceClient("", ""), ["ETHUSDT"], {}, {}, force=True)
    assert result["state"] == "not_configured" and "BINANCE_API_KEY" in result["message"]
