"""
AuditEvent model — immutable append-only audit log for all critical actions.
Covers: auth events, classification decisions, archive/label mutations, draft generation, undo operations.
Immutability enforced at DB level via trigger (see migration) + S3 Object Lock for exports.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_user_created", "user_id", "created_at"),
        Index("ix_audit_mailbox_created", "mailbox_id", "created_at"),
        Index("ix_audit_event_type", "event_type"),
        Index("ix_audit_correlation", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mailbox_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment=(
            "auth.connect | auth.disconnect | triage.decision | "
            "mutation.archive | mutation.label | mutation.undo | "
            "draft.generated | draft.discarded | brief.delivered | "
            "memory.write | policy.update | safety.block"
        )
    )
    actor: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="system | user | worker:<name>"
    )
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Full event payload — never redacted in audit log
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    severity: Mapped[str] = mapped_column(
        String(20), default="info", nullable=False,
        comment="info | warn | critical"
    )
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Immutable timestamp — server-set only
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditEvent id={self.id} type={self.event_type} actor={self.actor}>"
