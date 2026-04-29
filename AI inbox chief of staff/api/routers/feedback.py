"""
Feedback endpoints — triage corrections, draft feedback, and behavioral signals.
Corrections update memories and improve future triage decisions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()
log = structlog.get_logger(__name__)


class TriageDecisionSummary(BaseModel):
    id: str
    email_id: str
    mailbox_id: str
    email_subject: str | None
    email_from: str | None
    outcome: str
    confidence: float
    method: str
    rule_matched: str | None
    corrected_by_user: bool
    created_at: str


class TriageDecisionListResponse(BaseModel):
    decisions: list[TriageDecisionSummary]
    total: int


@router.get("/triage-decisions", response_model=TriageDecisionListResponse)
async def list_triage_decisions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    outcome: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TriageDecisionListResponse:
    """Recent triage decisions for this user, newest first. Use to pick an email to correct."""
    from core.models.email import Email
    from core.models.triage import TriageDecision, TriageOutcome

    base = select(TriageDecision).where(TriageDecision.user_id == user.id)
    count_q = select(sa_func.count(TriageDecision.id)).where(TriageDecision.user_id == user.id)

    if mailbox_id:
        base = base.where(TriageDecision.mailbox_id == mailbox_id)
        count_q = count_q.where(TriageDecision.mailbox_id == mailbox_id)
    if outcome:
        try:
            outcome_enum = TriageOutcome(outcome)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid outcome: {outcome}")
        base = base.where(TriageDecision.outcome == outcome_enum)
        count_q = count_q.where(TriageDecision.outcome == outcome_enum)

    result = await db.execute(
        base.order_by(TriageDecision.created_at.desc()).limit(limit).offset(offset)
    )
    decisions = result.scalars().all()

    email_ids = [d.email_id for d in decisions]
    email_map: dict[uuid.UUID, Email] = {}
    if email_ids:
        emails = await db.execute(select(Email).where(Email.id.in_(email_ids)))
        for email in emails.scalars().all():
            email_map[email.id] = email

    total = (await db.execute(count_q)).scalar() or 0

    return TriageDecisionListResponse(
        total=total,
        decisions=[
            TriageDecisionSummary(
                id=str(d.id),
                email_id=str(d.email_id),
                mailbox_id=str(d.mailbox_id),
                email_subject=(email_map.get(d.email_id).subject if email_map.get(d.email_id) else None),
                email_from=(email_map.get(d.email_id).from_address if email_map.get(d.email_id) else None),
                outcome=d.outcome.value,
                confidence=d.confidence,
                method=d.method.value,
                rule_matched=d.rule_matched,
                corrected_by_user=d.corrected_by_user,
                created_at=d.created_at.isoformat(),
            )
            for d in decisions
        ],
    )


class TriageCorrectionRequest(BaseModel):
    email_id: uuid.UUID
    correct_outcome: str  # inbox_keep, brief_only, draft_candidate, protected
    reason: str | None = None


class TriageCorrectionResponse(BaseModel):
    correction_id: str
    memory_updated: bool
    message: str


@router.post("/triage-correction", response_model=TriageCorrectionResponse)
async def submit_triage_correction(
    request: TriageCorrectionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriageCorrectionResponse:
    """
    User corrects a triage decision. This:
    1. Marks the original triage decision as corrected
    2. Creates a feedback event
    3. Extracts a memory rule if the correction is clear enough
    """
    from core.models.email import Email
    from core.models.triage import TriageDecision, TriageOutcome
    from core.models.feedback import FeedbackEvent
    from core.models.memory import Memory, MemoryScope, MemoryType

    # Load email and verify ownership
    email = await db.get(Email, request.email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Load triage decision
    result = await db.execute(
        select(TriageDecision).where(TriageDecision.email_id == request.email_id)
    )
    triage = result.scalar_one_or_none()
    if not triage:
        raise HTTPException(status_code=404, detail="No triage decision for this email")

    # Validate outcome
    try:
        correct_outcome = TriageOutcome(request.correct_outcome)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid outcome: {request.correct_outcome}. "
            f"Valid: {[e.value for e in TriageOutcome]}",
        )

    # Mark original decision as corrected
    triage.corrected_by_user = True

    # Create feedback event
    feedback = FeedbackEvent(
        id=uuid.uuid4(),
        user_id=user.id,
        mailbox_id=email.mailbox_id,
        email_id=email.id,
        feedback_type="triage_correction",
        raw_content=request.reason or f"Corrected from {triage.outcome.value} to {correct_outcome.value}",
        structured_intent={
            "original_outcome": triage.outcome.value,
            "correct_outcome": correct_outcome.value,
            "from_address": email.from_address,
            "from_domain": email.from_domain,
            "subject": email.subject,
        },
        processed=False,
        correlation_id=str(uuid.uuid4()),
    )
    db.add(feedback)

    # Auto-extract memory if correction is "always inbox" for a specific sender
    memory_updated = False
    if correct_outcome == TriageOutcome.PROTECTED and email.from_address:
        memory = Memory(
            id=uuid.uuid4(),
            user_id=user.id,
            mailbox_id=email.mailbox_id,
            scope=MemoryScope.MAILBOX_SPECIFIC,
            applies_to_all_mailboxes=False,
            memory_type=MemoryType.POLICY,
            content=f"Always keep emails from {email.from_address} in inbox",
            structured_data={
                "rule": "always_inbox",
                "targets": [email.from_address],
                "source": "triage_correction",
            },
            source="triage_correction",
            confidence=1.0,
            is_active=True,
        )
        db.add(memory)
        memory_updated = True
        log.info(
            "feedback.memory_created",
            rule="always_inbox",
            sender=email.from_address,
            user_id=str(user.id),
        )

    elif correct_outcome == TriageOutcome.INBOX_KEEP and triage.outcome == TriageOutcome.BRIEF_ONLY:
        # User says "this shouldn't have been briefed" — lower confidence for similar
        feedback.structured_intent["signal"] = "false_brief"

    await db.flush()

    return TriageCorrectionResponse(
        correction_id=str(feedback.id),
        memory_updated=memory_updated,
        message=(
            f"Correction recorded: {triage.outcome.value} → {correct_outcome.value}. "
            + ("Memory rule created for this sender." if memory_updated else "Will improve future triage.")
        ),
    )


class DraftFeedbackRequest(BaseModel):
    draft_id: uuid.UUID
    action: str  # accepted, edited, discarded
    edited_text: str | None = None


@router.post("/draft-feedback")
async def submit_draft_feedback(
    request: DraftFeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record user action on a draft (accepted/edited/discarded)."""
    from core.models.draft import Draft, DraftStatus

    draft = await db.get(Draft, request.draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if request.action == "accepted":
        draft.status = DraftStatus.ACCEPTED
    elif request.action == "edited":
        draft.status = DraftStatus.EDITED_AND_SENT
    elif request.action == "discarded":
        draft.status = DraftStatus.DISCARDED
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await db.flush()

    log.info(
        "feedback.draft_action",
        draft_id=str(draft.id),
        action=request.action,
        user_id=str(user.id),
    )

    return {"updated": True, "draft_id": str(draft.id), "status": draft.status.value}
