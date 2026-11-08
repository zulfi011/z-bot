"""Signed requests to Binance's spot API.

Only this module knows the API secret. It never logs or returns the key or the secret, and every Binance error
code is translated into a sentence the dashboard can show. Timestamps are corrected with Binance's server clock so
a slow server clock cannot reject every request.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from app.services.ipv4_http import urlopen_ipv4

TIMEOUT = 10.0
# Binance error codes worth explaining in the dashboard.
MESSAGES = {
    -2015: "Binance rejected the API key. Check three things: the key is copied correctly, the needed permission "
           "is enabled, and its IP restriction lists this server's IPv4 address — the one shown under System "
           "health, 'Binance trading API'.",
    -2014: "The API key format is wrong — copy it again from Binance.",
    -1022: "The request signature was rejected — the API secret is probably wrong or has extra spaces.",
    -1021: "This server's clock is out of step with Binance. It retries with Binance's time automatically.",
    -1121: "Binance does not know that trading pair.",
    -2010: "Binance refused the order (not enough balance, or the amount is below its minimum).",
    -1013: "The order does not meet Binance's size or step rules for that pair.",
    -1003: "Too many requests to Binance — the app will slow down and retry.",
}


class BinanceError(RuntimeError):
    """A Binance rejection, with a plain-language explanation."""

    def __init__(self, code: int | None, message: str, status: int | None = None) -> None:
        self.code = code
        self.binance_message = message
        self.status = status
        super().__init__(MESSAGES.get(code or 0, message))

    @property
    def explanation(self) -> str:
        return str(self)


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.binance.com",
                 recv_window_ms: int = 5000) -> None:
        self._key = api_key.strip()
        self._secret = api_secret.strip().encode()
        self.base_url = base_url.rstrip("/")
        self.recv_window_ms = recv_window_ms
        self._time_offset_ms = 0
        self._offset_checked_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._key and self._secret)

    # ------------------------------------------------------------------ plumbing
    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
        query = dict(params or {})
        if signed:
            query["timestamp"] = int(time.time() * 1000) + self._time_offset_ms
            query["recvWindow"] = self.recv_window_ms
            encoded = urlencode(query)
            query["signature"] = hmac.new(self._secret, encoded.encode(), hashlib.sha256).hexdigest()
            encoded = f"{encoded}&signature={query['signature']}"
        else:
            encoded = urlencode(query)
        url = f"{self.base_url}{path}" + (f"?{encoded}" if encoded else "")
        request = Request(url, method=method, headers={"X-MBX-APIKEY": self._key} if self._key else {})
        try:
            with urlopen_ipv4(request, timeout=TIMEOUT) as response:
                return json.loads(response.read() or b"null")
        except HTTPError as error:
            body = error.read()
            try:
                payload = json.loads(body)
                raise BinanceError(payload.get("code"), str(payload.get("msg", body[:200])), error.code) from None
            except (ValueError, AttributeError):
                raise BinanceError(None, body[:200].decode("utf-8", "replace"), error.code) from None
        except (URLError, TimeoutError, OSError) as error:
            raise BinanceError(None, f"Could not reach Binance: {error}") from None

    def _synchronize_clock(self) -> None:
        """Binance rejects requests whose timestamp drifts; re-check the offset every few minutes."""
        if time.monotonic() - self._offset_checked_at < 300:
            return
        server_time = int(self._request("GET", "/api/v3/time")["serverTime"])
        self._time_offset_ms = server_time - int(time.time() * 1000)
        self._offset_checked_at = time.monotonic()

    def signed_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            raise BinanceError(None, "No Binance API key is configured on this server.")
        self._synchronize_clock()
        try:
            return self._request("GET", path, params, signed=True)
        except BinanceError as error:
            if error.code == -1021:  # clock drifted since the last check
                self._offset_checked_at = 0.0
                self._synchronize_clock()
                return self._request("GET", path, params, signed=True)
            raise

    def signed_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        """Signed POST/DELETE (placing and cancelling orders)."""
        if not self.configured:
            raise BinanceError(None, "No Binance API key is configured on this server.")
        self._synchronize_clock()
        return self._request(method, path, params, signed=True)

    # ------------------------------------------------------------------ read-only calls
    def account(self) -> dict:
        return self.signed_get("/api/v3/account", {"omitZeroBalances": "true"})

    def api_restrictions(self) -> dict:
        return self.signed_get("/sapi/v1/account/apiRestrictions")

    def bnb_burn(self) -> dict:
        return self.signed_get("/sapi/v1/bnbBurn")

    def commission(self, symbol: str) -> dict:
        return self.signed_get("/api/v3/account/commission", {"symbol": symbol})
