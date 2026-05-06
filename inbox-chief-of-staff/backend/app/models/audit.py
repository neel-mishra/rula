"""AuditEvent and EvalSample ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable audit log entry for every agent action and policy decision.

    Every call through ``ActionPolicy.enforce`` writes an ``AuditEvent``
    regardless of whether the action was allowed or denied.  This provides
    a tamper-evident trail for compliance and debugging.
    """

    __tablename__ = "audit_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)  # "allowed" | "denied" | "error"
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)


class EvalSample(UUIDPrimaryKeyMixin, Base):
    """Recorded agent input/output sample for offline evaluation.

    Triage and draft samples are stored here so that human labels can be
    attached later and precision/recall/acceptance metrics computed.
    """

    __tablename__ = "eval_samples"

    sample_type: Mapped[str] = mapped_column(String(50), nullable=False)   # triage | draft | brief
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    output_hash: Mapped[str] = mapped_column(Text, nullable=False)
    human_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_output: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
