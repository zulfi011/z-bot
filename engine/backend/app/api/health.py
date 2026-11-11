"""Health checks, alerts and the system log."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.settings import get_settings
from app.core.strategy import load_strategies
from app.db.session import get_engine
from app.services.account import read_settings

router = APIRouter()


# ------------------------------------------------------------------- reads
@router.get("/health/live")
def liveness() -> dict:
    return {"status": "ok", "service": "api", "version": get_settings().app_version}


@router.get("/health/ready")
def readiness() -> dict:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            mode = str(read_settings(connection).get("trading_mode", "shadow"))
        strategies = load_strategies()
    except (SQLAlchemyError, OSError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail="Application is not ready") from error
    return {"status": "ready", "services": {"api": "ok", "database": "ok", "strategy_config": "ok"},
            "strategies": {symbol: strategy["strategy_id"] for symbol, strategy in strategies.items()},
            "trading_mode": mode}


@router.get("/monitoring/alerts")
def monitoring_alerts(include_resolved: bool = False) -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT * FROM monitoring_alerts WHERE :r OR status='active' ORDER BY last_seen_at DESC"),
            {"r": include_resolved},
        ).mappings().all()
    return {"alerts": [dict(row) for row in rows]}


@router.get("/monitoring/logs")
def monitoring_logs(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT id, timestamp, level, component, event_type, details FROM system_events ORDER BY timestamp DESC LIMIT :l"),
            {"l": limit},
        ).mappings().all()
    return {"logs": [dict(row) for row in rows]}
