"""Draft model — voice-aligned reply drafts, written to Gmail Drafts only (never sent)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class DraftStatus(str, PyEnum):
    GENERATED = "generated"          # written to Gmail Drafts
    ACCEPTED = "accepted"            # user sent it (we observe sent label change)
    EDITED_AND_SENT = "edited_and_sent"
    REJECTED = "rejected"              # below grounding threshold, not pushed to Gmail
    DISCARDED = "discarded"
    FAILED = "failed"


class Draft(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        Index("ix_drafts_mailbox_created", "mailbox_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Gmail draft reference
    gmail_draft_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Draft content
    draft_text: Mapped[str] = mapped_column(Text, nullable=False)
    subject_line: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Provenance
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    style_profile_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Quality signals
    grounding_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    style_conformance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Lifecycle
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus), default=DraftStatus.GENERATED, nullable=False, index=True
    )

    # Correlation
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Edit tracking: captures diff between generated draft and what user actually sent
    user_edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    edit_distance: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="0.0=completely different, 1.0=identical"
    )
    edits_tracked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

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
    email: Mapped["Email"] = relationship("Email", back_populates="draft")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Draft id={self.id} status={self.status} mailbox={self.mailbox_id}>"
