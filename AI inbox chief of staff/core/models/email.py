"""
Email model — canonical email representation, scoped strictly by mailbox_id.
Gmail thread/message IDs are only unique within a mailbox.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

from core.db import Base


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        Index("ix_emails_mailbox_received", "mailbox_id", "received_at"),
        Index("ix_emails_mailbox_gmail_message", "mailbox_id", "gmail_message_id", unique=True),
        Index("ix_emails_mailbox_thread", "mailbox_id", "gmail_thread_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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

    # Gmail identifiers
    gmail_message_id: Mapped[str] = mapped_column(String(100), nullable=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # Headers / metadata
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    to_addresses: Mapped[list] = mapped_column(ARRAY(Text), default=list, nullable=False)
    cc_addresses: Mapped[list] = mapped_column(ARRAY(Text), default=list, nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Content
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)    # sanitized plain text
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)    # sanitized HTML

    # Gmail labels at time of ingestion
    gmail_labels: Mapped[list] = mapped_column(ARRAY(Text), default=list, nullable=False)

    # Extracted text from attachments (one dict per attachment; see core/email/attachments.py)
    attachment_extracts: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False
    )

    # Thread metadata
    thread_message_count: Mapped[int] = mapped_column(default=1, nullable=False)
    is_thread_root: Mapped[bool] = mapped_column(default=True, nullable=False)
    parent_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Timestamps
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Derived features
    features: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="Computed features: is_reply, is_newsletter, sender_vip, etc."
    )

    # pgvector embedding for RAG retrieval (1536-dim, text-embedding-3-small)
    embedding = mapped_column(Vector(1536), nullable=True) if Vector else None

    # Relationships
    mailbox: Mapped["Mailbox"] = relationship("Mailbox", back_populates="emails")  # noqa: F821
    triage_decision: Mapped["TriageDecision | None"] = relationship(  # noqa: F821
        "TriageDecision", back_populates="email", uselist=False, cascade="all, delete-orphan"
    )
    draft: Mapped["Draft | None"] = relationship(  # noqa: F821
        "Draft", back_populates="email", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Email id={self.id} gmail_id={self.gmail_message_id} mailbox={self.mailbox_id}>"
