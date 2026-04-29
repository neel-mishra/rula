"""Admin-only API for gold-eval fixture management.

Mounted under `/admin/gold-eval`. Every route requires admin role.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db
from core.models.gold_sample import (
    GoldDatasetVersion,
    GoldFixtureType,
    GoldSample,
    GoldSampleLabel,
    GoldStratum,
)
from core.models.user import User
from core.security.auth import require_admin
from workers.gold_sample_extraction import extract_gold_samples

router = APIRouter()


class ExtractRequest(BaseModel):
    mailbox_id: str
    dry_run: bool = True


class ExtractResponse(BaseModel):
    status: str
    mailbox_id: str
    samples_persisted: int
    per_stratum: dict[str, int] | None = None
    reason: str | None = None


@router.post("/extract", response_model=ExtractResponse)
async def trigger_extract(
    request: ExtractRequest,
    _admin: User = Depends(require_admin),
) -> ExtractResponse:
    if not settings.gold_sampling_enabled:
        return ExtractResponse(
            status="deferred",
            mailbox_id=request.mailbox_id,
            samples_persisted=0,
            reason="gold_sampling_enabled=False; flip this in settings once OAuth is live",
        )
    try:
        mailbox_id = uuid.UUID(request.mailbox_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid mailbox_id")
    result = await extract_gold_samples(
        mailbox_id=mailbox_id,
        dry_run=request.dry_run,
    )
    return ExtractResponse(
        status=result.get("status", "ok"),
        mailbox_id=request.mailbox_id,
        samples_persisted=result.get("samples_persisted", 0),
        per_stratum=result.get("per_stratum"),
        reason=result.get("reason"),
    )


class SampleSummary(BaseModel):
    id: str
    fixture_type: str
    stratum: str
    label_count: int
    subject_preview: str


@router.get("/samples", response_model=list[SampleSummary])
async def list_samples(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    fixture_type: str | None = Query(None),
    unlabeled: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
) -> list[SampleSummary]:
    q = select(GoldSample).where(GoldSample.is_active.is_(True))
    if fixture_type:
        try:
            q = q.where(GoldSample.fixture_type == GoldFixtureType(fixture_type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown fixture_type: {fixture_type}")
    q = q.order_by(GoldSample.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    out: list[SampleSummary] = []
    for r in rows:
        labels = (
            await db.execute(
                select(GoldSampleLabel).where(GoldSampleLabel.gold_sample_id == r.id)
            )
        ).scalars().all()
        if unlabeled and labels:
            continue
        out.append(
            SampleSummary(
                id=str(r.id),
                fixture_type=r.fixture_type.value,
                stratum=r.stratum.value,
                label_count=len(labels),
                subject_preview=(r.scrubbed_payload or {}).get("subject", "")[:80],
            )
        )
    return out


class LabelRequest(BaseModel):
    label_type: str
    labels: dict[str, Any]
    rationale: str | None = None


class LabelResponse(BaseModel):
    label_id: str
    sample_id: str


@router.post("/samples/{sample_id}/label", response_model=LabelResponse)
async def label_sample(
    sample_id: str,
    request: LabelRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> LabelResponse:
    try:
        sid = uuid.UUID(sample_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sample_id")
    sample = await db.get(GoldSample, sid)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    row = GoldSampleLabel(
        id=uuid.uuid4(),
        gold_sample_id=sample.id,
        label_type=request.label_type,
        labeled_by_user_id=admin.id,
        labels=request.labels,
        rationale=request.rationale,
    )
    db.add(row)
    await db.flush()
    return LabelResponse(label_id=str(row.id), sample_id=str(sample.id))


class DatasetCutRequest(BaseModel):
    tag: str
    notes: str | None = None


class DatasetVersionResponse(BaseModel):
    id: str
    tag: str
    is_latest: bool
    sample_count: int


@router.post("/datasets", response_model=DatasetVersionResponse)
async def cut_dataset(
    request: DatasetCutRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DatasetVersionResponse:
    active_q = await db.execute(
        select(GoldSample.id).where(GoldSample.is_active.is_(True))
    )
    ids = [str(row[0]) for row in active_q.all()]
    version = GoldDatasetVersion(
        id=uuid.uuid4(),
        tag=request.tag,
        notes=request.notes,
        is_latest=False,
        sample_ids=ids,
    )
    db.add(version)
    await db.flush()
    return DatasetVersionResponse(
        id=str(version.id),
        tag=version.tag,
        is_latest=False,
        sample_count=len(ids),
    )


@router.post("/datasets/{tag}/activate", response_model=DatasetVersionResponse)
async def activate_dataset(
    tag: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DatasetVersionResponse:
    await db.execute(update(GoldDatasetVersion).values(is_latest=False))
    target_q = await db.execute(
        select(GoldDatasetVersion).where(GoldDatasetVersion.tag == tag)
    )
    target = target_q.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail=f"Tag {tag} not found")
    target.is_latest = True
    await db.flush()
    return DatasetVersionResponse(
        id=str(target.id),
        tag=target.tag,
        is_latest=True,
        sample_count=len(target.sample_ids),
    )
