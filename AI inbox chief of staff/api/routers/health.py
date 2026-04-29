"""Health check endpoints — required for ALB target group and Gate 0."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="inbox-chief-of-staff",
        version="0.1.0",
    )


@router.get("/ready")
async def readiness_check() -> dict:
    """Deep readiness: checks DB + Redis connectivity."""
    from core.db import engine
    from sqlalchemy import text

    checks: dict[str, str] = {}

    # DB check
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    # Redis check
    try:
        import redis.asyncio as aioredis
        from core.config import settings
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
