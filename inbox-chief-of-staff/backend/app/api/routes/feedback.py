"""User feedback collection endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.auth import get_current_user_id
from app.core.db import DBSession
from app.repositories.audit_repo import AuditRepository
from app.repositories.eval_repo import EvalRepository
from app.telemetry.events import _sha256

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/triage", summary="Record triage priority correction")
async def triage_feedback(
    body: dict,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Record that the user believes the AI assigned the wrong triage priority.

    The feedback is persisted to the eval dataset and routed to the
    EvalHarness for offline metric computation.
    """
    message_id = body.get("message_id")
    corrected_priority = body.get("corrected_priority")

    if not message_id or corrected_priority not in ("urgent", "normal", "brief", "archive"):
        raise HTTPException(
            status_code=422,
            detail="message_id and valid corrected_priority required",
        )

    eval_repo = EvalRepository(db)
    await eval_repo.create_sample(
        sample_type="triage",
        input_hash=_sha256({"message_id": message_id}),
        output_hash=_sha256({"corrected_priority": corrected_priority}),
        model_output={},
        human_label=corrected_priority,
    )

    audit_repo = AuditRepository(db)
    await audit_repo.create(
        user_id=user_id,
        event_type="user_feedback",
        action="triage_correction",
        outcome="recorded",
        metadata={"message_id": message_id, "corrected_priority": corrected_priority},
    )

    return {"status": "recorded"}


@router.post("/draft", summary="Record draft quality feedback")
async def draft_feedback(
    body: dict,
    db: DBSession,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Record the user's acceptance/rejection of a draft plus optional notes.

    Acceptance rate and quality scores feed into EvalHarness.compute_draft_acceptance_rate.
    """
    draft_id = body.get("draft_id")
    rating = body.get("rating")

    if not draft_id or rating not in ("helpful", "unhelpful"):
        raise HTTPException(
            status_code=422,
            detail="draft_id and rating (helpful|unhelpful) required",
        )

    eval_repo = EvalRepository(db)
    await eval_repo.create_sample(
        sample_type="draft",
        input_hash=_sha256({"draft_id": draft_id}),
        output_hash=_sha256({"rating": rating}),
        model_output={},
        score=1.0 if rating == "helpful" else 0.0,
    )

    audit_repo = AuditRepository(db)
    await audit_repo.create(
        user_id=user_id,
        event_type="user_feedback",
        action="draft_rating",
        outcome="recorded",
        metadata={"draft_id": draft_id, "rating": rating, "notes": body.get("notes")},
    )

    return {"status": "recorded"}
