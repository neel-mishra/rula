"""Launch SLO status endpoint — aggregates the numeric launch targets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.user import User
from core.security.auth import get_current_user
from core.slo import MetricReading, MetricStatus
from core.slo.metrics import collect_all

router = APIRouter()


class MetricOut(BaseModel):
    id: str
    name: str
    category: str
    target_value: float
    operator: str
    unit: str
    description: str
    value: float | None
    sample_size: int
    status: str
    note: str | None


class SLOStatusResponse(BaseModel):
    window_days: int
    metrics: list[MetricOut]
    summary: dict[str, int]     # {pass: N, warn: N, fail: N, not_measured: N}
    launch_ready: bool          # critical metrics all PASS


# Critical metrics gate the launch decision (per PRODUCT_ROADMAP Launch
# Decision Rule): false-archive, prompt-injection, undo success.
_CRITICAL_METRIC_IDS = {
    "false_archive_rate",
    "prompt_injection_pass_rate",
    "undo_success_rate",
}


def _to_out(reading: MetricReading) -> MetricOut:
    t = reading.target
    return MetricOut(
        id=t.id,
        name=t.name,
        category=t.category.value,
        target_value=t.target_value,
        operator=t.operator.value,
        unit=t.unit,
        description=t.description,
        value=reading.value,
        sample_size=reading.sample_size,
        status=reading.status.value,
        note=reading.note,
    )


@router.get("/status", response_model=SLOStatusResponse)
async def get_slo_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    window_days: int = Query(7, ge=1, le=90),
) -> SLOStatusResponse:
    readings = await collect_all(db, user.id, window_days)
    summary = {s.value: 0 for s in MetricStatus}
    for r in readings:
        summary[r.status.value] += 1

    critical_readings = [r for r in readings if r.target.id in _CRITICAL_METRIC_IDS]
    launch_ready = all(r.status == MetricStatus.PASS for r in critical_readings)

    return SLOStatusResponse(
        window_days=window_days,
        metrics=[_to_out(r) for r in readings],
        summary=summary,
        launch_ready=launch_ready,
    )
