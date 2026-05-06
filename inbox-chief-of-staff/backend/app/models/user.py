"""User and MailboxConnection ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MailboxStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    error = "error"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Represents an authenticated end-user.

    ``google_refresh_token`` is stored encrypted at rest via
    ``app.core.security.encrypt_token`` / ``decrypt_token``.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    google_refresh_token: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    # Relationships
    mailbox_connections: Mapped[list[MailboxConnection]] = relationship(
        "MailboxConnection", back_populates="user", cascade="all, delete-orphan"
    )


class MailboxConnection(UUIDPrimaryKeyMixin, Base):
    """Tracks a Gmail mailbox connected to a user account."""

    __tablename__ = "mailbox_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gmail_address: Mapped[str] = mapped_column(String(320), nullable=False)
    watch_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MailboxStatus] = mapped_column(
        Enum(MailboxStatus, name="mailbox_status"),
        nullable=False,
        default=MailboxStatus.inactive,
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="mailbox_connections")
