"""Where the Binance API key lives.

Keys attached from the dashboard are written to one small file (owner-only permissions) in the `secrets` volume,
never to the database, so database backups and the public stats export can never contain them. Keys set in the
environment (BINANCE_API_KEY / BINANCE_API_SECRET) still work; a key attached from the dashboard takes precedence.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.core.settings import get_settings

_lock = threading.Lock()
_cache: tuple[float, tuple[str, str] | None] | None = None


def _path() -> Path:
    return Path(get_settings().binance_credentials_path)


def from_file() -> tuple[str, str] | None:
    """The key attached from the dashboard, re-read only when the file changes."""
    global _cache
    path = _path()
    try:
        modified = path.stat().st_mtime
    except OSError:
        _cache = None
        return None
    with _lock:
        if _cache and _cache[0] == modified:
            return _cache[1]
    try:
        data = json.loads(path.read_text())
        found = (str(data["api_key"]).strip(), str(data["api_secret"]).strip())
        found = found if all(found) else None
    except (OSError, ValueError, KeyError, TypeError):
        found = None
    with _lock:
        _cache = (modified, found)
    return found


def current() -> tuple[str, str] | None:
    """The key in use: the dashboard's, else the environment's, else none."""
    found = from_file()
    if found:
        return found
    settings = get_settings()
    key, secret = settings.binance_api_key.strip(), settings.binance_api_secret.strip()
    return (key, secret) if key and secret else None


def source() -> str | None:
    if from_file():
        return "dashboard"
    return "environment" if current() else None


def attached() -> bool:
    return current() is not None


def hint(key: str) -> str:
    return f"{key[:4]}…{key[-4:]}" if len(key) > 8 else "…"


def save(api_key: str, api_secret: str) -> None:
    """Write atomically with owner-only permissions."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"api_key": api_key.strip(), "api_secret": api_secret.strip()}, handle)
    os.replace(temporary, path)


def remove() -> None:
    try:
        _path().unlink()
    except FileNotFoundError:
        pass
