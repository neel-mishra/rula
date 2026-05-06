"""Health check endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.db import DBSession

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/live", summary="Liveness probe")
async def liveness() -> dict:
    """Return 200 immediately — confirms the process is alive."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def readiness(db: DBSession, response: Response) -> dict:
    """Check database connectivity.

    Returns 200 with ``{"status": "ok", "db": "ok"}`` when ready,
    or 503 with ``{"status": "error", "db": "unreachable"}`` otherwise.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        logger.error("readiness_check_failed", error=str(exc))
        response.status_code = 503
        return {"status": "error", "db": "unreachable"}
