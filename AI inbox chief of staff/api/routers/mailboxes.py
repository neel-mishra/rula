"""Mailbox management endpoints — list, get, update per-mailbox settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.mailbox import Mailbox
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class MailboxSummary(BaseModel):
    id: str
    gmail_email: str
    is_connected: bool
    is_active: bool
    brief_enabled: bool
    draft_enabled: bool
    auto_archive_enabled: bool
    brief_morning_hour: int | None
    brief_afternoon_hour: int | None
    activation_mode: str
    gmail_watch_expiration: str | None


class UpdateMailboxSettings(BaseModel):
    brief_enabled: bool | None = None
    draft_enabled: bool | None = None
    auto_archive_enabled: bool | None = None
    brief_morning_hour: int | None = None
    brief_afternoon_hour: int | None = None
    activation_mode: str | None = None  # shadow | observe | auto


def _to_summary(m: Mailbox) -> MailboxSummary:
    return MailboxSummary(
        id=str(m.id),
        gmail_email=m.gmail_email,
        is_connected=m.is_connected,
        is_active=m.is_active,
        brief_enabled=m.brief_enabled,
        draft_enabled=m.draft_enabled,
        auto_archive_enabled=m.auto_archive_enabled,
        brief_morning_hour=m.brief_morning_hour,
        brief_afternoon_hour=m.brief_afternoon_hour,
        activation_mode=m.activation_mode if hasattr(m, "activation_mode") else "shadow",
        gmail_watch_expiration=m.gmail_watch_expiration.isoformat() if m.gmail_watch_expiration else None,
    )


@router.get("/", response_model=list[MailboxSummary])
async def list_mailboxes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MailboxSummary]:
    """List all connected mailboxes for the authenticated user."""
    result = await db.execute(
        select(Mailbox).where(Mailbox.user_id == user.id, Mailbox.is_active == True)  # noqa: E712
    )
    return [_to_summary(m) for m in result.scalars().all()]


@router.get("/{mailbox_id}", response_model=MailboxSummary)
async def get_mailbox(
    mailbox_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MailboxSummary:
    mailbox = await db.get(Mailbox, mailbox_id)
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    if mailbox.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your mailbox")
    return _to_summary(mailbox)


@router.patch("/{mailbox_id}/settings")
async def update_mailbox_settings(
    mailbox_id: uuid.UUID,
    settings_update: UpdateMailboxSettings,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    mailbox = await db.get(Mailbox, mailbox_id)
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    if mailbox.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your mailbox")

    if settings_update.brief_enabled is not None:
        mailbox.brief_enabled = settings_update.brief_enabled
    if settings_update.draft_enabled is not None:
        mailbox.draft_enabled = settings_update.draft_enabled
    if settings_update.auto_archive_enabled is not None:
        mailbox.auto_archive_enabled = settings_update.auto_archive_enabled
    if settings_update.brief_morning_hour is not None:
        if not 0 <= settings_update.brief_morning_hour <= 23:
            raise HTTPException(status_code=400, detail="brief_morning_hour must be 0-23")
        mailbox.brief_morning_hour = settings_update.brief_morning_hour
    if settings_update.brief_afternoon_hour is not None:
        if not 0 <= settings_update.brief_afternoon_hour <= 23:
            raise HTTPException(status_code=400, detail="brief_afternoon_hour must be 0-23")
        mailbox.brief_afternoon_hour = settings_update.brief_afternoon_hour
    if settings_update.activation_mode is not None:
        if settings_update.activation_mode not in ("shadow", "observe", "auto"):
            raise HTTPException(status_code=400, detail="activation_mode must be shadow, observe, or auto")
        mailbox.activation_mode = settings_update.activation_mode

    return {"updated": True}
