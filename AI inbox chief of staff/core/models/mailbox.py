"""
Mailbox model — one row per connected Gmail address.
Each mailbox has its own OAuth tokens, watch subscription, and label namespace.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class Mailbox(Base):
    __tablename__ = "mailboxes"
    __table_args__ = (
        Index("ix_mailboxes_user_id_email", "user_id", "gmail_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gmail_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    gmail_user_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Google sub / userId

    # OAuth tokens — stored encrypted at rest (application-level envelope encryption)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Gmail watch state
    gmail_watch_expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    gmail_history_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gmail_watch_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Labels created by this system (per-mailbox; Gmail labelId unique per account)
    label_needs_attention: Mapped[str | None] = mapped_column(String(100), nullable=True)
    label_next_brief: Mapped[str | None] = mapped_column(String(100), nullable=True)
    label_cora_system: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Per-mailbox feature flags and preferences
    feature_flags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    brief_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    draft_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_archive_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    brief_morning_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brief_afternoon_hour: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Rollout: shadow → observe → auto
    activation_mode: Mapped[str] = mapped_column(
        String(20), default="shadow", nullable=False,
        comment="shadow=log only | observe=log+label | auto=full automation"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    backfill_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="mailboxes")  # noqa: F821
    emails: Mapped[list["Email"]] = relationship(  # noqa: F821
        "Email", back_populates="mailbox", cascade="all, delete-orphan"
    )
    briefs: Mapped[list["Brief"]] = relationship(  # noqa: F821
        "Brief", back_populates="mailbox", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Mailbox id={self.id} email={self.gmail_email}>"
