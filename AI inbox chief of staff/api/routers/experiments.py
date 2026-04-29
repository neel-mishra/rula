"""Experiment management endpoints — A/B testing over versioned prompts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.db import get_db
from core.models.experiment import (
    Experiment,
    ExperimentMetric,
    ExperimentStatus,
    ExperimentVariant,
)
from core.models.user import User
from core.prompts.experiments import rollup_experiment
from core.prompts.registry import get_prompt_registry
from core.security.auth import get_current_user

router = APIRouter()


class VariantCreate(BaseModel):
    label: str
    prompt_version: str
    traffic_pct: int = Field(ge=0, le=100)
    is_control: bool = False


class ExperimentCreate(BaseModel):
    name: str
    description: str | None = None
    prompt_name: str
    primary_metric: str  # one of ExperimentMetric values
    variants: list[VariantCreate]


class VariantOut(BaseModel):
    id: str
    label: str
    prompt_version: str
    traffic_pct: int
    is_control: bool


class ExperimentOut(BaseModel):
    id: str
    name: str
    description: str | None
    prompt_name: str
    primary_metric: str
    status: str
    started_at: str | None
    stopped_at: str | None
    created_at: str
    updated_at: str
    variants: list[VariantOut]


class ExperimentListResponse(BaseModel):
    experiments: list[ExperimentOut]
    total: int


class ExperimentUpdate(BaseModel):
    status: str | None = None  # active | paused | completed
    name: str | None = None
    description: str | None = None


class VariantStatsOut(BaseModel):
    variant_id: str
    label: str
    prompt_version: str
    is_control: bool
    traffic_pct: int
    sample_size: int
    metric_value: float | None
    correction_count: int | None
    acceptance_count: int | None
    avg_confidence: float | None
    z_score_vs_control: float | None
    p_value_vs_control: float | None
    is_significant: bool


class ExperimentRollupOut(BaseModel):
    experiment_id: str
    primary_metric: str
    window_start: str | None
    window_end: str
    variants: list[VariantStatsOut]
    winner_variant_id: str | None
    notes: list[str]


def _to_out(e: Experiment) -> ExperimentOut:
    return ExperimentOut(
        id=str(e.id),
        name=e.name,
        description=e.description,
        prompt_name=e.prompt_name,
        primary_metric=e.primary_metric.value,
        status=e.status.value,
        started_at=e.started_at.isoformat() if e.started_at else None,
        stopped_at=e.stopped_at.isoformat() if e.stopped_at else None,
        created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat(),
        variants=[
            VariantOut(
                id=str(v.id),
                label=v.label,
                prompt_version=v.prompt_version,
                traffic_pct=v.traffic_pct,
                is_control=v.is_control,
            )
            for v in sorted(e.variants, key=lambda x: x.created_at)
        ],
    )


@router.get("/", response_model=ExperimentListResponse)
async def list_experiments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None),
    prompt_name: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ExperimentListResponse:
    base = (
        select(Experiment)
        .where(Experiment.user_id == user.id)
        .options(selectinload(Experiment.variants))
    )
    count_q = select(sa_func.count(Experiment.id)).where(
        Experiment.user_id == user.id
    )

    if status:
        try:
            status_enum = ExperimentStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        base = base.where(Experiment.status == status_enum)
        count_q = count_q.where(Experiment.status == status_enum)
    if prompt_name:
        base = base.where(Experiment.prompt_name == prompt_name)
        count_q = count_q.where(Experiment.prompt_name == prompt_name)

    result = await db.execute(
        base.order_by(Experiment.created_at.desc()).limit(limit).offset(offset)
    )
    experiments = result.scalars().unique().all()
    total = (await db.execute(count_q)).scalar() or 0

    return ExperimentListResponse(
        total=total,
        experiments=[_to_out(e) for e in experiments],
    )


@router.post("/", response_model=ExperimentOut)
async def create_experiment(
    req: ExperimentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    # Validate primary_metric
    try:
        metric = ExperimentMetric(req.primary_metric)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid primary_metric: {req.primary_metric}",
        )

    # Validate variants
    if len(req.variants) < 2:
        raise HTTPException(
            status_code=400, detail="Experiment requires at least 2 variants"
        )
    total_traffic = sum(v.traffic_pct for v in req.variants)
    if total_traffic != 100:
        raise HTTPException(
            status_code=400,
            detail=f"Variant traffic_pct must sum to 100 (got {total_traffic})",
        )
    control_count = sum(1 for v in req.variants if v.is_control)
    if control_count != 1:
        raise HTTPException(
            status_code=400,
            detail="Exactly one variant must be marked is_control=true",
        )

    # Validate prompt_name + versions exist in registry
    registry = get_prompt_registry()
    known_versions = {
        pv.version for pv in registry.list_versions(req.prompt_name)
    }
    if not known_versions:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown prompt_name in registry: {req.prompt_name}",
        )
    for v in req.variants:
        if v.prompt_version not in known_versions:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"prompt_version '{v.prompt_version}' not registered "
                    f"for prompt '{req.prompt_name}'. "
                    f"Known: {sorted(known_versions)}"
                ),
            )

    experiment = Experiment(
        id=uuid.uuid4(),
        user_id=user.id,
        name=req.name,
        description=req.description,
        prompt_name=req.prompt_name,
        primary_metric=metric,
        status=ExperimentStatus.DRAFT,
    )
    db.add(experiment)
    await db.flush()

    for v in req.variants:
        variant = ExperimentVariant(
            id=uuid.uuid4(),
            experiment_id=experiment.id,
            label=v.label,
            prompt_version=v.prompt_version,
            traffic_pct=v.traffic_pct,
            is_control=v.is_control,
        )
        db.add(variant)

    await db.flush()

    # Reload with variants
    reloaded = await db.execute(
        select(Experiment)
        .where(Experiment.id == experiment.id)
        .options(selectinload(Experiment.variants))
    )
    return _to_out(reloaded.scalar_one())


@router.get("/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(
    experiment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    result = await db.execute(
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.variants))
    )
    experiment = result.scalar_one_or_none()
    if not experiment or experiment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _to_out(experiment)


@router.patch("/{experiment_id}", response_model=ExperimentOut)
async def update_experiment(
    experiment_id: uuid.UUID,
    update: ExperimentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentOut:
    result = await db.execute(
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.variants))
    )
    experiment = result.scalar_one_or_none()
    if not experiment or experiment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Experiment not found")

    now = datetime.now(tz=timezone.utc)

    if update.status is not None:
        try:
            new_status = ExperimentStatus(update.status)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {update.status}"
            )
        old_status = experiment.status
        experiment.status = new_status
        if (
            new_status == ExperimentStatus.ACTIVE
            and old_status != ExperimentStatus.ACTIVE
            and experiment.started_at is None
        ):
            experiment.started_at = now
        if new_status == ExperimentStatus.COMPLETED:
            experiment.stopped_at = now

    if update.name is not None:
        experiment.name = update.name
    if update.description is not None:
        experiment.description = update.description

    await db.flush()
    # Reload to avoid lazy-load on variants after onupdate refresh
    reloaded = await db.execute(
        select(Experiment)
        .where(Experiment.id == experiment.id)
        .options(selectinload(Experiment.variants))
    )
    return _to_out(reloaded.scalar_one())


@router.delete("/{experiment_id}")
async def delete_experiment(
    experiment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    experiment = await db.get(Experiment, experiment_id)
    if not experiment or experiment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Experiment not found")
    await db.delete(experiment)
    return {"deleted": True, "experiment_id": str(experiment_id)}


@router.get("/{experiment_id}/results", response_model=ExperimentRollupOut)
async def get_experiment_results(
    experiment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExperimentRollupOut:
    result = await db.execute(
        select(Experiment)
        .where(Experiment.id == experiment_id)
        .options(selectinload(Experiment.variants))
    )
    experiment = result.scalar_one_or_none()
    if not experiment or experiment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Experiment not found")

    rollup = await rollup_experiment(experiment, db)
    return ExperimentRollupOut(
        experiment_id=rollup.experiment_id,
        primary_metric=rollup.primary_metric,
        window_start=rollup.window_start,
        window_end=rollup.window_end,
        winner_variant_id=rollup.winner_variant_id,
        notes=rollup.notes,
        variants=[
            VariantStatsOut(
                variant_id=s.variant_id,
                label=s.label,
                prompt_version=s.prompt_version,
                is_control=s.is_control,
                traffic_pct=s.traffic_pct,
                sample_size=s.sample_size,
                metric_value=s.metric_value,
                correction_count=s.correction_count,
                acceptance_count=s.acceptance_count,
                avg_confidence=s.avg_confidence,
                z_score_vs_control=s.z_score_vs_control,
                p_value_vs_control=s.p_value_vs_control,
                is_significant=s.is_significant,
            )
            for s in rollup.variants
        ],
    )


class RegistryPromptOut(BaseModel):
    name: str
    active_version: str | None
    versions: list[str]


@router.get("/registry/prompts", response_model=list[RegistryPromptOut])
async def list_registry_prompts(
    user: User = Depends(get_current_user),
) -> list[RegistryPromptOut]:
    """Prompts available in the registry — used to populate the experiment form."""
    registry = get_prompt_registry()
    dump = registry.to_dict()
    return [
        RegistryPromptOut(
            name=name,
            active_version=info.get("active"),
            versions=list(info.get("versions", {}).keys()),
        )
        for name, info in sorted(dump.items())
    ]
