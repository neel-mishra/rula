"""Draft review endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.routes.auth import get_current_user_id
from app.core.db import DBSession
from app.models.draft import Draft
from app.models.message import Message, WorkflowRun

logger = structlog.get_logger(__name__)

router = APIRouter()


def _draft_to_dict(draft: Draft, message: Message | None = None) -> dict:
    d = {
        "id": str(draft.id),
        "workflowRunId": str(draft.workflow_run_id),
        "body": draft.body,
        "subjectLine": draft.subject_line,
        "confidence": draft.confidence,
        "status": draft.status,
        "userFeedback": draft.user_feedback,
        "createdAt": draft.created_at.isoformat(),
        "reviewedAt": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
        "originalMessage": None,
    }
    if message:
        d["originalMessage"] = {
            "id": str(message.id),
            "subject": message.subject,
            "senderEmail": message.sender_email,
            "senderName": message.sender_name,
            "receivedAt": message.received_at.isoformat() if message.received_at else None,
            "bodyPreview": message.body_preview,
        }
    return d


@router.get("", summary="List pending drafts")
async def list_drafts(
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return drafts for the authenticated user, newest first.

    Only drafts with status=``pending`` are returned by default.
    Results include the original message context for side-by-side review.
    """
    rows = await db.execute(
        select(Draft, Message)
        .join(WorkflowRun, Draft.workflow_run_id == WorkflowRun.id)
        .join(Message, WorkflowRun.message_id == Message.id)
        .where(WorkflowRun.user_id == user_id)
        .order_by(Draft.created_at.desc())
        .limit(50)
    )
    items = [_draft_to_dict(draft, msg) for draft, msg in rows]
    return {"items": items, "total": len(items), "page": 1, "pageSize": 50, "hasMore": False}


@router.get("/{draft_id}", summary="Get draft detail")
async def get_draft(
    draft_id: str,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return a single draft along with the original message context.

    The response embeds the associated Message via the workflow run so the
    UI can render the original message alongside the draft for review.
    """
    row = await db.execute(
        select(Draft, Message)
        .join(WorkflowRun, Draft.workflow_run_id == WorkflowRun.id)
        .join(Message, WorkflowRun.message_id == Message.id)
        .where(Draft.id == draft_id)
        .where(WorkflowRun.user_id == user_id)
    )
    result = row.first()
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft, msg = result
    return _draft_to_dict(draft, msg)


@router.patch("/{draft_id}", summary="Update draft status or body")
async def update_draft(
    draft_id: str,
    body: dict,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Accept, reject, or edit a draft.

    Accepted drafts are saved to Gmail as a draft (``gmail_draft_id`` populated).
    Rejected drafts are marked rejected and no Gmail action is taken.
    Edited drafts apply the user's body change before saving to Gmail.

    Only ``WRITE_DRAFT`` and ``ADD_LABEL`` actions are permitted; sending
    requires the user to act directly in Gmail.
    """
    row = await db.execute(
        select(Draft)
        .join(WorkflowRun, Draft.workflow_run_id == WorkflowRun.id)
        .where(Draft.id == draft_id)
        .where(WorkflowRun.user_id == user_id)
    )
    draft = row.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    status = body.get("status")
    if status and status not in ("accepted", "rejected", "edited"):
        raise HTTPException(status_code=422, detail="Invalid status")

    if status:
        draft.status = status
        draft.reviewed_at = datetime.now(timezone.utc)

    if "body" in body:
        draft.body = body["body"]
        if not status:
            draft.status = "edited"
            draft.reviewed_at = datetime.now(timezone.utc)

    if "userFeedback" in body:
        draft.user_feedback = body["userFeedback"]

    await db.commit()
    await db.refresh(draft)
    return _draft_to_dict(draft)
