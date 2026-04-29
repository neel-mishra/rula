"""Gold-eval sample + label + dataset-version models.

Populated only after Gmail OAuth + connectors are live in production.
The schema lives now so migrations + admin endpoints can ship ahead of
the data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class GoldFixtureType(str, PyEnum):
    TRIAGE = "triage"
    DRAFT = "draft"
    BRIEF = "brief"
    MEMORY = "memory"
    SAFETY = "safety"


class GoldStratum(str, PyEnum):
    NEWSLETTER = "newsletter"
    DIRECT_REPLY = "direct_reply"
    UPDATE = "update"
    ACTION_REQUIRED = "action_required"
    CALENDAR = "calendar"
    AMBIGUOUS = "ambiguous"


class GoldSample(Base):
    __tablename__ = "gold_samples"
    __table_args__ = (
        Index(
            "ix_gold_samples_mailbox_type",
            "mailbox_id", "fixture_type", "is_active",
        ),
        Index(
            "ix_gold_samples_stratum",
            "fixture_type", "stratum", "is_active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    fixture_type: Mapped[GoldFixtureType] = mapped_column(
        Enum(GoldFixtureType, name="goldfixturetype"), nullable=False
    )
    stratum: Mapped[GoldStratum] = mapped_column(
        Enum(GoldStratum, name="goldstratum"), nullable=False
    )
    source_gmail_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scrubbed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scrub_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    labels: Mapped[list["GoldSampleLabel"]] = relationship(
        "GoldSampleLabel", back_populates="sample", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<GoldSample id={self.id} fixture={self.fixture_type.value} "
            f"stratum={self.stratum.value}>"
        )


class GoldSampleLabel(Base):
    __tablename__ = "gold_sample_labels"
    __table_args__ = (
        Index("ix_gold_sample_labels_sample_type", "gold_sample_id", "label_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    gold_sample_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gold_samples.id", ondelete="CASCADE"),
        nullable=False,
    )
    label_type: Mapped[str] = mapped_column(String(40), nullable=False)
    labeled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    labels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sample: Mapped["GoldSample"] = relationship("GoldSample", back_populates="labels")


class GoldDatasetVersion(Base):
    __tablename__ = "gold_dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tag: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sample_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<GoldDatasetVersion tag={self.tag} latest={self.is_latest}>"
