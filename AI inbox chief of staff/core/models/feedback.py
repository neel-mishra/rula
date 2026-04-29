"""FeedbackEvent model — user corrections and assistant instructions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    __table_args__ = (
        Index("ix_feedback_mailbox_created", "mailbox_id", "created_at"),
        Index("ix_feedback_user_type", "user_id", "feedback_type"),
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
    # NULL for global/user-level feedback
    mailbox_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Related email, if applicable
    email_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="SET NULL"),
        nullable=True,
    )

    feedback_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="triage_correction | draft_rejection | assistant_instruction | undo_mutation | manual_reclassification"
    )
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_intent: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Processing status
    processed: Mapped[bool] = mapped_column(default=False, nullable=False)
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Memory record created from this feedback"
    )

    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<FeedbackEvent id={self.id} type={self.feedback_type}>"
