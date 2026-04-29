"""TriageDecision model — records every classification decision with full provenance."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class TriageOutcome(str, PyEnum):
    INBOX_KEEP = "inbox_keep"
    BRIEF_ONLY = "brief_only"
    DRAFT_CANDIDATE = "draft_candidate"
    MANUAL_REVIEW = "manual_review"      # low confidence; routed to review queue
    PROTECTED = "protected"              # "always inbox" rule; never archived


class TriageMethod(str, PyEnum):
    DETERMINISTIC = "deterministic"      # rule-engine only
    LLM = "llm"                          # LLM classification
    HYBRID = "hybrid"                    # rules + LLM combined
    FALLBACK = "fallback"                # LLM unavailable; fell back to deterministic


class TriageDecision(Base):
    __tablename__ = "triage_decisions"
    __table_args__ = (
        Index("ix_triage_mailbox_created", "mailbox_id", "created_at"),
        Index("ix_triage_outcome", "mailbox_id", "outcome"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
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

    # Decision fields
    outcome: Mapped[TriageOutcome] = mapped_column(
        Enum(TriageOutcome), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[TriageMethod] = mapped_column(Enum(TriageMethod), nullable=False)

    # Provenance
    rule_matched: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Reasoning trace (LLM reasoning or rule explanation)
    reason_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extended data
    extra: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Human correction
    corrected_by_user: Mapped[bool] = mapped_column(default=False, nullable=False)
    corrected_outcome: Mapped[TriageOutcome | None] = mapped_column(
        Enum(TriageOutcome), nullable=True
    )

    # Correlation
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

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
    email: Mapped["Email"] = relationship("Email", back_populates="triage_decision")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<TriageDecision id={self.id} outcome={self.outcome} "
            f"confidence={self.confidence:.2f} mailbox={self.mailbox_id}>"
        )
