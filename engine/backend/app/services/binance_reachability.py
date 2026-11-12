"""Can this server reach Binance's trading API?

Market data comes from Binance's public data hosts, which work almost everywhere. Account and order calls go to
api.binance.com, which answers HTTP 451 ("restricted location") from blocked countries such as the US. This check
calls a public endpoint on that host (no API key involved) so the dashboard can show whether live trading would
work from where the app is running, and which public IP address Binance sees.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request

from app.services.ipv4_http import urlopen_ipv4

TRADING_API = "https://api.binance.com/api/v3/time"
PUBLIC_IP = "https://api.ipify.org?format=json"
CACHE_SECONDS = 300

_lock = Lock()
_cached: tuple[float, dict] | None = None


def _get(url: str, timeout: float) -> tuple[int, bytes]:
    request = Request(url, headers={"User-Agent": "z-bot-reachability/1"})
    try:
        with urlopen_ipv4(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _probe(timeout: float = 5.0) -> dict:
    result: dict = {"checked_at": datetime.now(timezone.utc).isoformat(), "endpoint": TRADING_API}
    try:
        status, body = _get(TRADING_API, timeout)
        result["status_code"] = status
        if status == 200:
            result.update(state="reachable", message="Binance's trading API answers from this server.")
        elif status == 451:
            result.update(state="blocked",
                          message="Binance refuses requests from this server's location (HTTP 451). "
                                  "Live trading needs a server in a country Binance allows.")
        elif status in (403, 418, 429):
            result.update(state="limited", message=f"Binance answered HTTP {status} (blocked or rate-limited).")
        else:
            result.update(state="error", message=f"Unexpected answer from Binance: HTTP {status}.")
        if status != 200:
            result["detail"] = body[:200].decode("utf-8", "replace")
    except (URLError, TimeoutError, OSError) as error:
        result.update(state="unreachable", message=f"Could not connect to Binance: {error}")
    try:
        status, body = _get(PUBLIC_IP, timeout)
        if status == 200:
            result["public_ip"] = json.loads(body).get("ip")
    except (URLError, TimeoutError, OSError, ValueError):
        pass
    return result


def check(force: bool = False) -> dict:
    """Latest reachability result, refreshed at most every CACHE_SECONDS."""
    global _cached
    with _lock:
        if not force and _cached and time.monotonic() - _cached[0] < CACHE_SECONDS:
            return _cached[1]
    result = _probe()
    with _lock:
        _cached = (time.monotonic(), result)
    return result
