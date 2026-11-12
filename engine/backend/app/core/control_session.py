"""Unlocking a device once instead of typing the control key into every action.

The browser trades the control key for a session cookie. The cookie holds only an expiry time and a signature; the
key itself never leaves the server again. The signature is made with a secret derived from the control key, so
changing STRATEGY_EDIT_TOKEN on the server locks every device at once.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from threading import Lock

COOKIE = "zbot_session"
LIFETIME_SECONDS = 30 * 24 * 3600

# Guessing the key: after FAILURE_LIMIT wrong tries from one address within FAILURE_WINDOW, that address must wait.
FAILURE_LIMIT = 5
FAILURE_WINDOW = 15 * 60
_failures: dict[str, list[float]] = {}
_failures_lock = Lock()


def _secret(control_key: str) -> bytes:
    return hashlib.sha256(b"z-bot-session\0" + control_key.encode()).digest()


def issue(control_key: str, now: float | None = None) -> tuple[str, int]:
    """A session token and the unix time it expires."""
    expires = int((now if now is not None else time.time()) + LIFETIME_SECONDS)
    signature = hmac.new(_secret(control_key), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}", expires


def expiry(token: str | None, control_key: str, now: float | None = None) -> int | None:
    """When a valid session ends, or None if the token is missing, forged, expired or from an older key."""
    if not token or not control_key or "." not in token:
        return None
    expires_text, signature = token.split(".", 1)
    if not expires_text.isdigit():
        return None
    expected = hmac.new(_secret(control_key), expires_text.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    expires = int(expires_text)
    return expires if expires > (now if now is not None else time.time()) else None


def key_matches(candidate: str | None, control_key: str) -> bool:
    return bool(candidate and control_key and secrets.compare_digest(candidate, control_key))


def blocked_for(address: str, now: float | None = None) -> int:
    """Seconds this address must wait before trying another key (0 = may try)."""
    now = now if now is not None else time.time()
    with _failures_lock:
        recent = [at for at in _failures.get(address, []) if now - at < FAILURE_WINDOW]
        _failures[address] = recent
        if len(recent) < FAILURE_LIMIT:
            return 0
        return int(FAILURE_WINDOW - (now - recent[0])) + 1


def record_failure(address: str, now: float | None = None) -> None:
    with _failures_lock:
        _failures.setdefault(address, []).append(now if now is not None else time.time())


def clear_failures(address: str) -> None:
    with _failures_lock:
        _failures.pop(address, None)
