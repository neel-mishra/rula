"""Draft review API — list generated drafts per mailbox with quality scores."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.draft import Draft, DraftStatus
from core.models.email import Email
from core.models.mailbox import Mailbox
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class DraftOut(BaseModel):
    id: str
    email_id: str
    mailbox_id: str
    subject_line: str | None
    draft_body: str | None
    status: str
    grounding_score: float | None
    hallucination_flag: bool
    style_conformance_score: float | None
    edit_distance: float | None
    gmail_draft_id: str | None
    email_from: str | None
    email_subject: str | None
    created_at: str | None
    updated_at: str | None


class DraftListResponse(BaseModel):
    drafts: list[DraftOut]
    total: int


@router.get("/", response_model=DraftListResponse)
async def list_drafts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = (
        select(Draft, Email.from_address, Email.subject)
        .join(Email, Draft.email_id == Email.id, isouter=True)
        .where(Draft.user_id == user.id)
        .order_by(Draft.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    count_query = select(func.count(Draft.id)).where(Draft.user_id == user.id)

    if mailbox_id:
        mb = await db.get(Mailbox, mailbox_id)
        if not mb or mb.user_id != user.id:
            raise HTTPException(404, "Mailbox not found")
        query = query.where(Draft.mailbox_id == mailbox_id)
        count_query = count_query.where(Draft.mailbox_id == mailbox_id)

    if status:
        try:
            status_enum = DraftStatus(status)
            query = query.where(Draft.status == status_enum)
            count_query = count_query.where(Draft.status == status_enum)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}")

    result = await db.execute(query)
    rows = result.all()
    total = (await db.execute(count_query)).scalar() or 0

    return DraftListResponse(
        total=total,
        drafts=[
            DraftOut(
                id=str(d.id),
                email_id=str(d.email_id),
                mailbox_id=str(d.mailbox_id),
                subject_line=d.subject_line,
                draft_body=d.draft_body if d.draft_body and len(d.draft_body) <= 2000 else (d.draft_body[:2000] + "..." if d.draft_body else None),
                status=d.status.value if d.status else "unknown",
                grounding_score=d.grounding_score,
                hallucination_flag=d.hallucination_flag or False,
                style_conformance_score=d.style_conformance_score,
                edit_distance=d.edit_distance,
                gmail_draft_id=d.gmail_draft_id,
                email_from=from_addr,
                email_subject=email_subj,
                created_at=d.created_at.isoformat() if d.created_at else None,
                updated_at=d.updated_at.isoformat() if d.updated_at else None,
            )
            for d, from_addr, email_subj in rows
        ],
    )
