"""Message listing, detail, and triage-override endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api.routes.auth import get_current_user_id
from app.core.db import DBSession
from app.models.message import Message, TriagePriority, TriageResult, WorkflowRun

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("", summary="List messages")
async def list_messages(
    db: DBSession,
    priority: TriagePriority | None = Query(None, description="Filter by triage priority"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return paginated messages for the authenticated user.

    Results include embedded triage result so the UI can render priority
    badges without extra round-trips.
    """
    offset = (page - 1) * page_size

    q = (
        select(Message, TriageResult)
        .outerjoin(WorkflowRun, WorkflowRun.message_id == Message.id)
        .outerjoin(TriageResult, TriageResult.workflow_run_id == WorkflowRun.id)
        .where(Message.user_id == user_id)
    )

    if priority:
        q = q.where(TriageResult.priority == priority)

    count_q = select(func.count()).select_from(q.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    q = q.order_by(Message.received_at.desc()).limit(page_size).offset(offset)
    rows = await db.execute(q)

    items = []
    for msg, triage in rows:
        item = {
            "id": str(msg.id),
            "gmailMessageId": msg.gmail_message_id,
            "gmailThreadId": msg.gmail_thread_id,
            "subject": msg.subject,
            "senderEmail": msg.sender_email,
            "senderName": msg.sender_name,
            "receivedAt": msg.received_at.isoformat() if msg.received_at else None,
            "bodyPreview": msg.body_preview,
            "workflowState": None,
            "triage": None,
        }
        if triage:
            item["triage"] = {
                "id": str(triage.id),
                "priority": triage.priority,
                "confidence": triage.confidence,
                "rationale": triage.rationale,
                "labels": triage.labels or [],
                "modelVersion": triage.model_version,
                "createdAt": triage.created_at.isoformat(),
            }
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": (offset + page_size) < total,
    }


@router.get("/{message_id}", summary="Get message detail")
async def get_message(
    message_id: str,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return a single message with its full triage result."""
    row = await db.execute(
        select(Message, TriageResult)
        .outerjoin(WorkflowRun, WorkflowRun.message_id == Message.id)
        .outerjoin(TriageResult, TriageResult.workflow_run_id == WorkflowRun.id)
        .where(Message.id == message_id)
        .where(Message.user_id == user_id)
    )
    result = row.first()
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")

    msg, triage = result
    item = {
        "id": str(msg.id),
        "gmailMessageId": msg.gmail_message_id,
        "gmailThreadId": msg.gmail_thread_id,
        "subject": msg.subject,
        "senderEmail": msg.sender_email,
        "senderName": msg.sender_name,
        "receivedAt": msg.received_at.isoformat() if msg.received_at else None,
        "bodyPreview": msg.body_preview,
        "workflowState": None,
        "triage": None,
    }
    if triage:
        item["triage"] = {
            "id": str(triage.id),
            "priority": triage.priority,
            "confidence": triage.confidence,
            "rationale": triage.rationale,
            "labels": triage.labels or [],
            "modelVersion": triage.model_version,
            "createdAt": triage.created_at.isoformat(),
        }
    return item


@router.post("/{message_id}/triage-override", summary="Override AI triage priority")
async def triage_override(
    message_id: str,
    body: dict,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Allow the user to correct the AI triage priority for a message.

    The override is applied to the existing TriageResult and recorded as an
    audit event.  The original AI confidence is preserved; model_version is
    updated to ``"human_override"``.
    """
    new_priority = body.get("priority")
    if new_priority not in ("urgent", "normal", "brief", "archive"):
        raise HTTPException(status_code=422, detail="Invalid priority value")

    # Verify message belongs to user
    msg_result = await db.execute(
        select(Message)
        .where(Message.id == message_id)
        .where(Message.user_id == user_id)
    )
    msg = msg_result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Update triage result if it exists
    run_result = await db.execute(
        select(WorkflowRun).where(WorkflowRun.message_id == message_id)
    )
    run = run_result.scalar_one_or_none()
    if run:
        triage_result = await db.execute(
            select(TriageResult).where(TriageResult.workflow_run_id == run.id)
        )
        triage = triage_result.scalar_one_or_none()
        if triage:
            triage.priority = new_priority
            triage.model_version = "human_override"
            await db.commit()

    # Record audit event
    from app.repositories.audit_repo import AuditRepository
    audit_repo = AuditRepository(db)
    await audit_repo.create(
        user_id=user_id,
        event_type="triage_override",
        action="override_priority",
        outcome="applied",
        metadata={"message_id": message_id, "new_priority": new_priority},
    )

    return {"status": "ok", "priority": new_priority}
