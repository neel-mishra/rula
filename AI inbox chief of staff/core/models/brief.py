"""Brief and BriefItem models — per-mailbox scheduled digests. No cross-mailbox mode."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class BriefWindow(str, PyEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"


class BriefStatus(str, PyEnum):
    PENDING = "pending"
    GENERATING = "generating"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    FAILED = "failed"
    SKIPPED = "skipped"              # no items in window; brief intentionally skipped


class Brief(Base):
    __tablename__ = "briefs"
    __table_args__ = (
        Index("ix_briefs_mailbox_scheduled", "mailbox_id", "scheduled_at"),
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

    window: Mapped[BriefWindow] = mapped_column(Enum(BriefWindow), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[BriefStatus] = mapped_column(
        Enum(BriefStatus), default=BriefStatus.PENDING, nullable=False, index=True
    )

    # Composed brief content
    subject_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Delivery
    delivery_email_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Provenance
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    mailbox: Mapped["Mailbox"] = relationship("Mailbox", back_populates="briefs")  # noqa: F821
    items: Mapped[list["BriefItem"]] = relationship(
        "BriefItem", back_populates="brief", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Brief id={self.id} window={self.window} status={self.status} mailbox={self.mailbox_id}>"


class BriefItem(Base):
    __tablename__ = "brief_items"
    __table_args__ = (
        Index("ix_brief_items_brief_id", "brief_id"),
        Index("ix_brief_items_mailbox", "mailbox_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("briefs.id", ondelete="CASCADE"),
        nullable=False,
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="SET NULL"),
        nullable=True,
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="newsletter | update | transaction | fyi | custom"
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    gmail_open_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    brief: Mapped["Brief"] = relationship("Brief", back_populates="items")

    def __repr__(self) -> str:
        return f"<BriefItem id={self.id} category={self.category} brief={self.brief_id}>"
