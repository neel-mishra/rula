"""
Admin endpoints — cross-user visibility for operator / support.

Every route requires `require_admin`. Non-admin callers get 403.
Scope is kept narrow on purpose: list users, cross-user activity stats,
and cross-user SLO rollup. Anything that mutates another user's state
stays out of scope for this first RBAC cut.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.audit import AuditEvent
from core.models.draft import Draft
from core.models.mailbox import Mailbox
from core.models.mutation_ledger import MutationLedger, MutationStatus
from core.models.triage import TriageDecision
from core.models.user import User, UserRole
from core.security.auth import require_admin

router = APIRouter()


class AdminUserSummary(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool
    mailbox_count: int
    created_at: str


class AdminUserListResponse(BaseModel):
    users: list[AdminUserSummary]
    total: int


class AdminActivityStats(BaseModel):
    total_users: int
    active_users_in_window: int     # users with >= 1 triage decision in the window
    total_mailboxes: int
    triage_decisions: int
    drafts_generated: int
    mutations_applied: int
    undos_performed: int
    corrections_submitted: int
    critical_audit_events: int
    window_days: int


@router.get("/users", response_model=AdminUserListResponse)
async def list_all_users(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AdminUserListResponse:
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    users = result.scalars().all()
    total = (await db.execute(select(sa_func.count(User.id)))).scalar() or 0

    mailbox_counts: dict = {}
    if users:
        mbx = await db.execute(
            select(Mailbox.user_id, sa_func.count(Mailbox.id))
            .where(Mailbox.user_id.in_([u.id for u in users]))
            .group_by(Mailbox.user_id)
        )
        mailbox_counts = dict(mbx.all())

    return AdminUserListResponse(
        total=total,
        users=[
            AdminUserSummary(
                id=str(u.id),
                email=u.email,
                display_name=u.display_name,
                role=u.role.value,
                is_active=u.is_active,
                mailbox_count=int(mailbox_counts.get(u.id, 0)),
                created_at=u.created_at.isoformat(),
            )
            for u in users
        ],
    )


@router.get("/activity-stats", response_model=AdminActivityStats)
async def get_cross_user_activity(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    window_days: int = Query(7, ge=1, le=90),
) -> AdminActivityStats:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=window_days)

    total_users = (await db.execute(select(sa_func.count(User.id)))).scalar() or 0
    total_mailboxes = (
        await db.execute(
            select(sa_func.count(Mailbox.id)).where(Mailbox.is_active.is_(True))
        )
    ).scalar() or 0

    triage_count = (
        await db.execute(
            select(sa_func.count(TriageDecision.id)).where(
                TriageDecision.created_at >= cutoff
            )
        )
    ).scalar() or 0

    active_users = (
        await db.execute(
            select(sa_func.count(sa_func.distinct(TriageDecision.user_id))).where(
                TriageDecision.created_at >= cutoff
            )
        )
    ).scalar() or 0

    drafts = (
        await db.execute(
            select(sa_func.count(Draft.id)).where(Draft.created_at >= cutoff)
        )
    ).scalar() or 0

    mutations_applied = (
        await db.execute(
            select(sa_func.count(MutationLedger.id)).where(
                MutationLedger.created_at >= cutoff,
                MutationLedger.status == MutationStatus.APPLIED,
            )
        )
    ).scalar() or 0
    undos = (
        await db.execute(
            select(sa_func.count(MutationLedger.id)).where(
                MutationLedger.created_at >= cutoff,
                MutationLedger.status == MutationStatus.UNDONE,
            )
        )
    ).scalar() or 0
    corrections = (
        await db.execute(
            select(sa_func.count(TriageDecision.id)).where(
                TriageDecision.created_at >= cutoff,
                TriageDecision.corrected_by_user.is_(True),
            )
        )
    ).scalar() or 0
    critical_events = (
        await db.execute(
            select(sa_func.count(AuditEvent.id)).where(
                AuditEvent.created_at >= cutoff,
                AuditEvent.severity == "critical",
            )
        )
    ).scalar() or 0

    return AdminActivityStats(
        total_users=total_users,
        active_users_in_window=int(active_users),
        total_mailboxes=int(total_mailboxes),
        triage_decisions=int(triage_count),
        drafts_generated=int(drafts),
        mutations_applied=int(mutations_applied),
        undos_performed=int(undos),
        corrections_submitted=int(corrections),
        critical_audit_events=int(critical_events),
        window_days=window_days,
    )


class RoleUpdate(BaseModel):
    role: str   # "user" | "admin"


class AdminUserUpdateResponse(BaseModel):
    id: str
    role: str


@router.patch("/users/{user_id}/role", response_model=AdminUserUpdateResponse)
async def set_user_role(
    user_id: str,
    update: RoleUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserUpdateResponse:
    import uuid

    try:
        target_id = uuid.UUID(user_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid user_id")
    try:
        new_role = UserRole(update.role)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid role: {update.role}")

    from fastapi import HTTPException
    target = await db.get(User, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and new_role != UserRole.ADMIN:
        raise HTTPException(
            status_code=400, detail="Admins cannot demote themselves"
        )
    target.role = new_role
    await db.flush()
    return AdminUserUpdateResponse(id=str(target.id), role=target.role.value)
