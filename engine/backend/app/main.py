from fastapi import FastAPI

from app.api.routes import router
from app.core.settings import get_settings


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Five coin strategies (SOL, ETH, BTC, AAVE, LINK) trading on a Binance spot account.",
)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"service": settings.app_name, "docs": "/docs", "health": "/api/v1/health/ready"}
