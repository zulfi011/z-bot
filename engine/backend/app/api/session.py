"""Unlocking the dashboard's controls on this device with the control key."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core import control_session
from app.core.settings import get_settings

router = APIRouter()


class UnlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=500)


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _secure_cookie(request: Request) -> bool:
    """HTTPS in front (Tailscale) means a Secure cookie; plain http on localhost for development does not."""
    origin = request.headers.get("origin", "")
    return (origin.startswith("https://") or request.headers.get("x-forwarded-proto") == "https"
            or request.url.scheme == "https" or request.url.hostname not in ("localhost", "127.0.0.1"))


@router.get("/session")
def session_status(session: str | None = Cookie(default=None, alias=control_session.COOKIE)) -> dict:
    configured = get_settings().strategy_edit_token
    expires = control_session.expiry(session, configured) if isinstance(session, str) else None
    return {"unlocked": expires is not None, "controls_enabled": bool(configured),
            "expires_at": datetime.fromtimestamp(expires, timezone.utc) if expires else None}


@router.post("/session")
def unlock(body: UnlockRequest, request: Request, response: Response) -> dict:
    """Trade the control key for a 30-day session cookie on this device."""
    configured = get_settings().strategy_edit_token
    if not configured:
        raise HTTPException(status_code=503, detail="Controls are disabled until STRATEGY_EDIT_TOKEN is set on the server")
    address = _client_address(request)
    wait = control_session.blocked_for(address)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many wrong keys. Try again in {max(1, wait // 60)} minute(s).")
    if not control_session.key_matches(body.key.strip(), configured):
        control_session.record_failure(address)
        raise HTTPException(status_code=403, detail="That is not the control key.")
    control_session.clear_failures(address)
    token, expires = control_session.issue(configured)
    response.set_cookie(control_session.COOKIE, token, max_age=control_session.LIFETIME_SECONDS, httponly=True,
                        secure=_secure_cookie(request), samesite="strict", path="/api")
    return {"unlocked": True, "expires_at": datetime.fromtimestamp(expires, timezone.utc)}


@router.delete("/session")
def lock(request: Request, response: Response) -> dict:
    response.delete_cookie(control_session.COOKIE, path="/api", httponly=True, secure=_secure_cookie(request),
                           samesite="strict")
    return {"unlocked": False}
