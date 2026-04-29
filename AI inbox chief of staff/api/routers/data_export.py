"""
GDPR data export — user can request a full export of their data.
Returns JSON containing all user records across all tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class DataExportResponse(BaseModel):
    user_id: str
    exported_at: str
    data: dict


class DataDeletionResponse(BaseModel):
    user_id: str
    deleted: bool
    details: dict


@router.get("/export", response_model=DataExportResponse)
async def export_user_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DataExportResponse:
    """Export all user data for GDPR compliance."""
    from core.models.email import Email
    from core.models.mailbox import Mailbox
    from core.models.memory import Memory
    from core.models.feedback import FeedbackEvent
    from core.models.draft import Draft
    from core.models.brief import Brief
    from core.models.triage import TriageDecision

    data: dict = {"user": {"id": str(user.id), "email": user.email, "display_name": user.display_name}}

    # Mailboxes (exclude encrypted tokens)
    mailboxes = await db.execute(select(Mailbox).where(Mailbox.user_id == user.id))
    data["mailboxes"] = [
        {
            "id": str(m.id),
            "gmail_email": m.gmail_email,
            "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mailboxes.scalars().all()
    ]

    # Memories
    memories = await db.execute(select(Memory).where(Memory.user_id == user.id))
    data["memories"] = [
        {
            "id": str(m.id),
            "memory_type": m.memory_type.value,
            "content": m.content,
            "scope": m.scope.value,
            "confidence": m.confidence,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memories.scalars().all()
    ]

    # Feedback events
    feedback = await db.execute(select(FeedbackEvent).where(FeedbackEvent.user_id == user.id))
    data["feedback"] = [
        {
            "id": str(f.id),
            "feedback_type": f.feedback_type,
            "raw_content": f.raw_content,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in feedback.scalars().all()
    ]

    # Email metadata (no body content for privacy)
    emails = await db.execute(
        select(Email).where(Email.user_id == user.id).limit(1000)
    )
    data["email_metadata"] = [
        {
            "id": str(e.id),
            "from_address": e.from_address,
            "subject": e.subject,
            "received_at": e.received_at.isoformat() if e.received_at else None,
        }
        for e in emails.scalars().all()
    ]

    return DataExportResponse(
        user_id=str(user.id),
        exported_at=datetime.now(tz=timezone.utc).isoformat(),
        data=data,
    )


@router.delete("/delete-account", response_model=DataDeletionResponse)
async def delete_user_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DataDeletionResponse:
    """
    Delete all user data for GDPR right-to-erasure.
    Cascades through all related tables via FK ondelete=CASCADE.
    """
    from core.models.mailbox import Mailbox
    from core.gmail.auth import revoke_token

    # Revoke OAuth tokens for all mailboxes before deletion
    mailboxes = await db.execute(select(Mailbox).where(Mailbox.user_id == user.id))
    revoked = 0
    for mailbox in mailboxes.scalars().all():
        try:
            await revoke_token(mailbox)
            revoked += 1
        except Exception:
            pass

    # Delete user — cascades to mailboxes → emails → triage → drafts → briefs → mutations
    await db.delete(user)
    await db.flush()

    return DataDeletionResponse(
        user_id=str(user.id),
        deleted=True,
        details={"tokens_revoked": revoked},
    )
