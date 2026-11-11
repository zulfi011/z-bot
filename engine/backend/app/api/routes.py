"""The dashboard API: one router under /api/v1, assembled from the topic modules beside this file."""

from fastapi import APIRouter

from app.api import binance, controls, dashboard, health, profit, session

router = APIRouter(prefix="/api/v1")
for module in (session, controls, binance, health, dashboard, profit):
    router.include_router(module.router)
