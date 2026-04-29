"""
Prompt experiments — A/B testing over versioned prompts from PromptRegistry.

Each Experiment targets one prompt_name (e.g. "triage_classifier") and defines
2+ variants, each pinned to a registered prompt_version. Mailboxes are assigned
to variants deterministically via hash(mailbox_id + experiment_id). Outcomes
are rolled up from the agents' existing writes to `prompt_version` on
TriageDecision / Draft / Brief.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class ExperimentStatus(str, PyEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class ExperimentMetric(str, PyEnum):
    """Which outcome we track as the primary success metric."""
    TRIAGE_CORRECTION_RATE = "triage_correction_rate"  # lower is better
    DRAFT_ACCEPTANCE_RATE = "draft_acceptance_rate"    # higher is better
    AVG_CONFIDENCE = "avg_confidence"                  # higher is better


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        Index("ix_experiments_status_prompt", "status", "prompt_name"),
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

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    prompt_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Matches PromptRegistry name, e.g. triage_classifier",
    )
    primary_metric: Mapped[ExperimentMetric] = mapped_column(
        Enum(ExperimentMetric), nullable=False
    )

    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus),
        default=ExperimentStatus.DRAFT,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    variants: Mapped[list["ExperimentVariant"]] = relationship(
        "ExperimentVariant",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentVariant.created_at",
    )


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"
    __table_args__ = (
        Index("ix_variant_experiment", "experiment_id"),
        CheckConstraint("traffic_pct >= 0 AND traffic_pct <= 100", name="ck_variant_traffic_pct"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Human label: 'control', 'variant_a', 'variant_b'",
    )
    prompt_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Matches a version registered in PromptRegistry for this prompt_name",
    )
    traffic_pct: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Share of eligible mailboxes routed here, 0-100",
    )
    is_control: Mapped[bool] = mapped_column(default=False, nullable=False)

    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    experiment: Mapped["Experiment"] = relationship(
        "Experiment", back_populates="variants"
    )
