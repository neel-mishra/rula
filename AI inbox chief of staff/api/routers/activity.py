"""Activity endpoints — aggregate stats, recent event feed, and the
unified per-mailbox transparency timeline (U.8) for the dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.audit import AuditEvent
from core.models.draft import Draft
from core.models.email import Email
from core.models.mutation_ledger import MutationLedger, MutationStatus
from core.models.triage import TriageDecision
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()

TimelineKind = Literal["triage", "mutation", "draft", "audit"]


class ActivityStats(BaseModel):
    emails_triaged: int
    drafts_generated: int
    mutations_applied: int
    undos_performed: int
    window_days: int


class ActivityEvent(BaseModel):
    id: str
    event_type: str
    actor: str
    resource_type: str | None
    resource_id: str | None
    severity: str
    mailbox_id: str | None
    created_at: str
    payload: dict


class ActivityEventsResponse(BaseModel):
    events: list[ActivityEvent]
    total: int


@router.get("/stats", response_model=ActivityStats)
async def get_activity_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    window_days: int = Query(7, ge=1, le=90),
) -> ActivityStats:
    """Aggregate activity counts for this user over the given window."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)

    def _user_filter(column_user_id):
        return column_user_id == user.id

    triage_q = select(sa_func.count(TriageDecision.id)).where(
        TriageDecision.user_id == user.id,
        TriageDecision.created_at >= cutoff,
    )
    drafts_q = select(sa_func.count(Draft.id)).where(
        Draft.user_id == user.id,
        Draft.created_at >= cutoff,
    )
    applied_q = select(sa_func.count(MutationLedger.id)).where(
        MutationLedger.user_id == user.id,
        MutationLedger.created_at >= cutoff,
        MutationLedger.status == MutationStatus.APPLIED,
    )
    undone_q = select(sa_func.count(MutationLedger.id)).where(
        MutationLedger.user_id == user.id,
        MutationLedger.created_at >= cutoff,
        MutationLedger.status == MutationStatus.UNDONE,
    )

    if mailbox_id:
        triage_q = triage_q.where(TriageDecision.mailbox_id == mailbox_id)
        drafts_q = drafts_q.where(Draft.mailbox_id == mailbox_id)
        applied_q = applied_q.where(MutationLedger.mailbox_id == mailbox_id)
        undone_q = undone_q.where(MutationLedger.mailbox_id == mailbox_id)

    emails_triaged = (await db.execute(triage_q)).scalar() or 0
    drafts_generated = (await db.execute(drafts_q)).scalar() or 0
    mutations_applied = (await db.execute(applied_q)).scalar() or 0
    undos_performed = (await db.execute(undone_q)).scalar() or 0

    return ActivityStats(
        emails_triaged=emails_triaged,
        drafts_generated=drafts_generated,
        mutations_applied=mutations_applied,
        undos_performed=undos_performed,
        window_days=window_days,
    )


@router.get("/events", response_model=ActivityEventsResponse)
async def list_activity_events(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    event_type_prefix: str | None = Query(None, description="e.g. 'mutation' or 'triage'"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ActivityEventsResponse:
    """Recent audit events for this user, newest first."""
    base = select(AuditEvent).where(AuditEvent.user_id == user.id)
    count_q = select(sa_func.count(AuditEvent.id)).where(AuditEvent.user_id == user.id)

    if mailbox_id:
        base = base.where(AuditEvent.mailbox_id == mailbox_id)
        count_q = count_q.where(AuditEvent.mailbox_id == mailbox_id)
    if event_type_prefix:
        pattern = f"{event_type_prefix}%"
        base = base.where(AuditEvent.event_type.like(pattern))
        count_q = count_q.where(AuditEvent.event_type.like(pattern))

    result = await db.execute(
        base.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
    )
    events = result.scalars().all()
    total = (await db.execute(count_q)).scalar() or 0

    return ActivityEventsResponse(
        total=total,
        events=[
            ActivityEvent(
                id=str(e.id),
                event_type=e.event_type,
                actor=e.actor,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                severity=e.severity,
                mailbox_id=str(e.mailbox_id) if e.mailbox_id else None,
                created_at=e.created_at.isoformat(),
                payload=e.payload or {},
            )
            for e in events
        ],
    )


# ── U.8 — Unified per-mailbox transparency timeline ───────────────────────


class TimelineItem(BaseModel):
    id: str
    kind: TimelineKind
    timestamp: str
    headline: str
    detail: str | None
    related_email_id: str | None = None
    related_email_subject: str | None = None
    related_email_from: str | None = None
    extra: dict = {}


class TimelineResponse(BaseModel):
    items: list[TimelineItem]
    mailbox_id: str
    next_before: str | None
    has_more: bool


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID = Query(..., description="Required — timeline is per-mailbox"),
    limit: int = Query(50, ge=5, le=200),
    before: datetime | None = Query(None, description="Cursor; return items strictly older than this"),
    kinds: str | None = Query(
        None,
        description="Comma-separated subset of triage,mutation,draft,audit",
    ),
) -> TimelineResponse:
    """
    Unified chronological feed of triage decisions, mutations, drafts, and
    audit events scoped to a single mailbox. Each row carries a uniform
    shape so the UI can render one timeline component for everything.
    """
    selected_kinds: set[str] = (
        {k.strip() for k in kinds.split(",") if k.strip()}
        if kinds
        else {"triage", "mutation", "draft", "audit"}
    )
    invalid = selected_kinds - {"triage", "mutation", "draft", "audit"}
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown kinds: {sorted(invalid)}")

    cutoff = before or datetime.now(tz=timezone.utc)
    per_source_limit = limit + 1   # +1 so we can detect has_more cheaply

    items: list[TimelineItem] = []

    # Pre-fetch related email metadata in one shot at the end to avoid N+1.
    email_ids: set[uuid.UUID] = set()

    if "triage" in selected_kinds:
        rows = (await db.execute(
            select(TriageDecision)
            .where(
                TriageDecision.user_id == user.id,
                TriageDecision.mailbox_id == mailbox_id,
                TriageDecision.created_at < cutoff,
            )
            .order_by(TriageDecision.created_at.desc())
            .limit(per_source_limit)
        )).scalars().all()
        for r in rows:
            email_ids.add(r.email_id)
            items.append(TimelineItem(
                id=f"triage:{r.id}",
                kind="triage",
                timestamp=r.created_at.isoformat(),
                headline=f"Triaged → {r.outcome.value.replace('_', ' ')}",
                detail=(
                    f"confidence {(r.confidence or 0) * 100:.0f}% · "
                    f"{r.method.value}"
                    + (f" · {r.rule_matched}" if r.rule_matched else "")
                    + (" · corrected" if r.corrected_by_user else "")
                ),
                related_email_id=str(r.email_id),
                extra={"corrected": r.corrected_by_user},
            ))

    if "mutation" in selected_kinds:
        rows = (await db.execute(
            select(MutationLedger)
            .where(
                MutationLedger.user_id == user.id,
                MutationLedger.mailbox_id == mailbox_id,
                MutationLedger.created_at < cutoff,
            )
            .order_by(MutationLedger.created_at.desc())
            .limit(per_source_limit)
        )).scalars().all()
        for r in rows:
            email_ids.add(r.email_id)
            items.append(TimelineItem(
                id=f"mutation:{r.id}",
                kind="mutation",
                timestamp=r.created_at.isoformat(),
                headline=f"{r.mutation_type.value.replace('_', ' ').title()} · {r.status.value}",
                detail=r.reason_trace,
                related_email_id=str(r.email_id),
                extra={
                    "status": r.status.value,
                    "undo_token": r.undo_token if r.status == MutationStatus.APPLIED else None,
                    "undo_expires_at": r.undo_expires_at.isoformat() if r.undo_expires_at else None,
                },
            ))

    if "draft" in selected_kinds:
        rows = (await db.execute(
            select(Draft)
            .where(
                Draft.user_id == user.id,
                Draft.mailbox_id == mailbox_id,
                Draft.created_at < cutoff,
            )
            .order_by(Draft.created_at.desc())
            .limit(per_source_limit)
        )).scalars().all()
        for r in rows:
            email_ids.add(r.email_id)
            items.append(TimelineItem(
                id=f"draft:{r.id}",
                kind="draft",
                timestamp=r.created_at.isoformat(),
                headline=f"Draft · {r.status.value}",
                detail=(
                    f"grounding {(r.grounding_score or 0) * 100:.0f}% · "
                    f"style {(r.style_conformance_score or 0) * 100:.0f}%"
                    + (" · hallucinated" if r.hallucination_flag else "")
                ),
                related_email_id=str(r.email_id),
                extra={
                    "grounding_score": r.grounding_score,
                    "style_conformance_score": r.style_conformance_score,
                    "hallucination_flag": r.hallucination_flag,
                },
            ))

    if "audit" in selected_kinds:
        rows = (await db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.user_id == user.id,
                AuditEvent.mailbox_id == mailbox_id,
                AuditEvent.created_at < cutoff,
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(per_source_limit)
        )).scalars().all()
        for r in rows:
            items.append(TimelineItem(
                id=f"audit:{r.id}",
                kind="audit",
                timestamp=r.created_at.isoformat(),
                headline=r.event_type,
                detail=f"actor: {r.actor}" + (f" · {r.resource_type}:{r.resource_id}" if r.resource_type else ""),
                extra={"severity": r.severity, "payload": r.payload or {}},
            ))

    # Hydrate related-email metadata in a single query.
    if email_ids:
        emails = (await db.execute(
            select(Email).where(Email.id.in_(email_ids))
        )).scalars().all()
        email_map: dict[uuid.UUID, Email] = {e.id: e for e in emails}
        for it in items:
            if it.related_email_id:
                eid = uuid.UUID(it.related_email_id)
                em = email_map.get(eid)
                if em:
                    it.related_email_subject = em.subject
                    it.related_email_from = em.from_address

    items.sort(key=lambda x: x.timestamp, reverse=True)
    has_more = len(items) > limit
    items = items[:limit]
    next_before = items[-1].timestamp if items and has_more else None

    return TimelineResponse(
        items=items,
        mailbox_id=str(mailbox_id),
        next_before=next_before,
        has_more=has_more,
    )
