import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.settings import get_settings


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Five coin strategies (SOL, ETH, BTC, AAVE, LINK) trading on a Binance spot account.",
)
app.include_router(router)

log = logging.getLogger("z-bot-api")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@app.middleware("http")
async def request_id(request: Request, call_next):
    """Every answer carries an X-Request-ID (the caller's own, if it sent a sensible one).

    A crash returns only that id, never a stack trace; the server log has the full error under the same id, so a
    reported id leads straight to it.
    """
    given = request.headers.get("x-request-id", "")
    rid = given if REQUEST_ID.match(given) else uuid.uuid4().hex[:12]
    request.state.request_id = rid
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error request_id=%s %s %s", rid, request.method, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": f"Internal server error (request_id={rid})"})
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/")
def root() -> dict:
    return {"service": settings.app_name, "docs": "/docs", "health": "/api/v1/health/ready"}
