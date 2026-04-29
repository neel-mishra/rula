"""
Memory model — persistent user preferences, routing rules, and style instructions.
Scope: mailbox_specific | user_global.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

from core.db import Base


class MemoryScope(str, PyEnum):
    MAILBOX_SPECIFIC = "mailbox_specific"   # applies only to one mailbox
    USER_GLOBAL = "user_global"             # applies_to_all_mailboxes=True


class MemoryType(str, PyEnum):
    PROFILE = "profile"        # who/what matters to the user
    POLICY = "policy"          # routing rules and preferences
    STYLE = "style"            # writing voice / tone instructions
    SENDER = "sender"          # sender-specific rules


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_scope", "user_id", "scope"),
        Index("ix_memories_mailbox_type", "mailbox_id", "memory_type"),
        Index("ix_memories_active", "user_id", "is_active"),
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
    # NULL when scope=user_global; required when scope=mailbox_specific
    mailbox_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    scope: Mapped[MemoryScope] = mapped_column(Enum(MemoryScope), nullable=False, index=True)
    applies_to_all_mailboxes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    memory_type: Mapped[MemoryType] = mapped_column(Enum(MemoryType), nullable=False, index=True)

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Provenance
    source: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="feedback | assistant_instruction | behavioral_signal | manual"
    )
    source_feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feedback_events.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Quality
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Freshness
    last_reinforced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # pgvector embedding for semantic search (1536-dim, text-embedding-3-small)
    embedding = mapped_column(Vector(1536), nullable=True) if Vector else None

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
    user: Mapped["User"] = relationship("User", back_populates="memories")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Memory id={self.id} type={self.memory_type} scope={self.scope} "
            f"active={self.is_active}>"
        )
