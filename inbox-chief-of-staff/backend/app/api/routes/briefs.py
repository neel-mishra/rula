"""Brief (daily digest) endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.routes.auth import get_current_user_id
from app.core.db import DBSession
from app.models.brief import Brief
from app.orchestrator.agent_dispatcher import run_brief_batch

logger = structlog.get_logger(__name__)

router = APIRouter()


def _brief_to_dict(brief: Brief) -> dict:
    return {
        "id": str(brief.id),
        "timeWindow": brief.time_window,
        "summaryMarkdown": brief.summary_markdown,
        "actionItems": [{"text": item} for item in (brief.action_items or [])],
        "messageIds": brief.message_ids or [],
        "createdAt": brief.created_at.isoformat(),
    }


@router.get("", summary="List briefs")
async def list_briefs(
    db: DBSession,
    limit: int = Query(10, ge=1, le=50, description="Latest N briefs per time window"),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return the most recent briefs for the authenticated user.

    Results are ordered newest first.  The client can group by ``time_window``
    to display morning / afternoon digests separately.
    """
    result = await db.execute(
        select(Brief)
        .where(Brief.user_id == user_id)
        .order_by(Brief.created_at.desc())
        .limit(limit)
    )
    items = [_brief_to_dict(b) for b in result.scalars().all()]
    return {"items": items, "total": len(items), "page": 1, "pageSize": limit, "hasMore": False}


@router.post("/generate", summary="Trigger brief generation")
async def generate_brief(
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
    time_window: Literal["morning", "afternoon"] | None = Query(
        None, description="Force a specific time window; auto-detected if omitted"
    ),
) -> dict:
    """Trigger on-demand brief generation for the authenticated user.

    If ``time_window`` is not supplied, it is auto-detected: ``morning`` before
    13:00 UTC, ``afternoon`` from 13:00 UTC onward.

    The underlying :func:`run_brief_batch` is a no-op when there are no
    ``BRIEF_QUEUED`` messages for the user; the endpoint still returns 200.
    """
    resolved_window: str = time_window or (
        "morning" if datetime.now(timezone.utc).hour < 13 else "afternoon"
    )

    await run_brief_batch(user_id=user_id, time_window=resolved_window, db=db)

    return {"status": "ok", "time_window": resolved_window}


@router.get("/{brief_id}", summary="Get brief detail")
async def get_brief(
    brief_id: str,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return a single brief by ID."""
    result = await db.execute(
        select(Brief)
        .where(Brief.id == brief_id)
        .where(Brief.user_id == user_id)
    )
    brief = result.scalar_one_or_none()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return _brief_to_dict(brief)
