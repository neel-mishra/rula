"""
MutationLedger — complete record of every system-initiated mailbox mutation.
Guarantees undo support within configured policy window.
Every archive/label action must have a ledger entry before execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class MutationType(str, PyEnum):
    ARCHIVE = "archive"
    LABEL_ADD = "label_add"
    LABEL_REMOVE = "label_remove"
    MARK_READ = "mark_read"


class MutationStatus(str, PyEnum):
    PENDING = "pending"
    APPLIED = "applied"
    UNDONE = "undone"
    UNDO_FAILED = "undo_failed"
    EXPIRED = "expired"       # past undo window


class MutationLedger(Base):
    __tablename__ = "mutation_ledger"
    __table_args__ = (
        Index("ix_mutation_mailbox_created", "mailbox_id", "created_at"),
        Index("ix_mutation_status", "status"),
        Index("ix_mutation_undo_token", "undo_token", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
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

    mutation_type: Mapped[MutationType] = mapped_column(Enum(MutationType), nullable=False)
    status: Mapped[MutationStatus] = mapped_column(
        Enum(MutationStatus), default=MutationStatus.PENDING, nullable=False, index=True
    )

    # State capture
    prior_state: Mapped[dict] = mapped_column(JSONB, nullable=False)   # labels before mutation
    new_state: Mapped[dict] = mapped_column(JSONB, nullable=False)     # labels after mutation
    label_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Provenance
    reason_trace: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    triage_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("triage_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Undo mechanics
    undo_token: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    undo_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    within_undo_window: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MutationLedger id={self.id} type={self.mutation_type} "
            f"status={self.status} mailbox={self.mailbox_id}>"
        )
