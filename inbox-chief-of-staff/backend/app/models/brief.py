"""Brief ORM model."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TimeWindow(str, enum.Enum):
    morning = "morning"
    afternoon = "afternoon"


class Brief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AI-generated digest of non-urgent emails for a given time window."""

    __tablename__ = "briefs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    time_window: Mapped[TimeWindow] = mapped_column(
        Enum(TimeWindow, name="time_window"),
        nullable=False,
    )
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    message_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
