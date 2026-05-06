"""Message, WorkflowRun, and TriageResult ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IngestStatus(str, enum.Enum):
    pending = "pending"
    normalized = "normalized"
    failed = "failed"


class WorkflowState(str, enum.Enum):
    ingested = "ingested"
    normalized = "normalized"
    triaged = "triaged"
    draft_queued = "draft_queued"
    brief_queued = "brief_queued"
    pending_review = "pending_review"
    completed = "completed"
    rejected = "rejected"


class TriagePriority(str, enum.Enum):
    urgent = "urgent"
    normal = "normal"
    brief = "brief"
    archive = "archive"


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single Gmail message ingested into the system."""

    __tablename__ = "messages"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="")
    sender_email: Mapped[str] = mapped_column(String(320), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    body_preview: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    raw_payload_gcs_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus, name="ingest_status"),
        nullable=False,
        default=IngestStatus.pending,
    )

    # Relationships
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        "WorkflowRun", back_populates="message", cascade="all, delete-orphan"
    )


class WorkflowRun(UUIDPrimaryKeyMixin, Base):
    """State machine instance tracking a single message through the pipeline."""

    __tablename__ = "workflow_runs"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[WorkflowState] = mapped_column(
        Enum(WorkflowState, name="workflow_state"),
        nullable=False,
        default=WorkflowState.ingested,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    message: Mapped[Message] = relationship("Message", back_populates="workflow_runs")
    triage_result: Mapped[TriageResult | None] = relationship(
        "TriageResult", back_populates="workflow_run", uselist=False
    )


class TriageResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AI-generated triage classification for a workflow run."""

    __tablename__ = "triage_results"

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    priority: Mapped[TriagePriority] = mapped_column(
        Enum(TriagePriority, name="triage_priority"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    # Relationships
    workflow_run: Mapped[WorkflowRun] = relationship("WorkflowRun", back_populates="triage_result")
