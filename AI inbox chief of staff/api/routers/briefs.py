"""Brief history API — list past briefs and their items per mailbox."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.db import get_db
from core.models.brief import Brief, BriefItem, BriefStatus, BriefWindow
from core.models.mailbox import Mailbox
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class BriefItemOut(BaseModel):
    id: str
    category: str | None
    summary: str | None
    key_points: list[str] | None
    gmail_open_url: str | None
    importance_score: float | None
    sort_order: int | None


class BriefOut(BaseModel):
    id: str
    mailbox_id: str
    window: str
    status: str
    subject_line: str | None
    item_count: int | None
    scheduled_at: str | None
    delivered_at: str | None
    created_at: str | None
    items: list[BriefItemOut]


class BriefListResponse(BaseModel):
    briefs: list[BriefOut]
    total: int


@router.get("/", response_model=BriefListResponse)
async def list_briefs(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = (
        select(Brief)
        .where(Brief.user_id == user.id)
        .options(selectinload(Brief.items))
        .order_by(Brief.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if mailbox_id:
        mb = await db.get(Mailbox, mailbox_id)
        if not mb or mb.user_id != user.id:
            raise HTTPException(404, "Mailbox not found")
        query = query.where(Brief.mailbox_id == mailbox_id)

    count_query = select(func.count(Brief.id)).where(Brief.user_id == user.id)
    if mailbox_id:
        count_query = count_query.where(Brief.mailbox_id == mailbox_id)

    result = await db.execute(query)
    briefs = result.scalars().unique().all()
    total = (await db.execute(count_query)).scalar() or 0

    return BriefListResponse(
        total=total,
        briefs=[
            BriefOut(
                id=str(b.id),
                mailbox_id=str(b.mailbox_id),
                window=b.window.value if b.window else "unknown",
                status=b.status.value if b.status else "unknown",
                subject_line=b.subject_line,
                item_count=b.item_count,
                scheduled_at=b.scheduled_at.isoformat() if b.scheduled_at else None,
                delivered_at=b.delivered_at.isoformat() if b.delivered_at else None,
                created_at=b.created_at.isoformat() if b.created_at else None,
                items=[
                    BriefItemOut(
                        id=str(item.id),
                        category=item.category,
                        summary=item.summary,
                        key_points=item.key_points if isinstance(item.key_points, list) else [],
                        gmail_open_url=item.gmail_open_url,
                        importance_score=item.importance_score,
                        sort_order=item.sort_order,
                    )
                    for item in sorted(b.items, key=lambda x: x.sort_order or 0)
                ],
            )
            for b in briefs
        ],
    )


@router.get("/{brief_id}", response_model=BriefOut)
async def get_brief(
    brief_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Brief)
        .where(Brief.id == brief_id)
        .options(selectinload(Brief.items))
    )
    brief = result.scalar_one_or_none()
    if not brief or brief.user_id != user.id:
        raise HTTPException(404, "Brief not found")

    return BriefOut(
        id=str(brief.id),
        mailbox_id=str(brief.mailbox_id),
        window=brief.window.value if brief.window else "unknown",
        status=brief.status.value if brief.status else "unknown",
        subject_line=brief.subject_line,
        item_count=brief.item_count,
        scheduled_at=brief.scheduled_at.isoformat() if brief.scheduled_at else None,
        delivered_at=brief.delivered_at.isoformat() if brief.delivered_at else None,
        created_at=brief.created_at.isoformat() if brief.created_at else None,
        items=[
            BriefItemOut(
                id=str(item.id),
                category=item.category,
                summary=item.summary,
                key_points=item.key_points if isinstance(item.key_points, list) else [],
                gmail_open_url=item.gmail_open_url,
                importance_score=item.importance_score,
                sort_order=item.sort_order,
            )
            for item in sorted(brief.items, key=lambda x: x.sort_order or 0)
        ],
    )
