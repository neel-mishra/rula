"""
Behavioral signal memory — observes user actions (undo, reclassify, draft edits)
and extracts implicit preferences as new memories.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from core.db import get_db_session
from core.models.draft import Draft, DraftStatus
from core.models.feedback import FeedbackEvent
from core.models.memory import Memory, MemoryScope, MemoryType
from core.models.mutation_ledger import MutationLedger, MutationStatus

log = structlog.get_logger(__name__)


async def run_behavioral_signal_extraction() -> dict:
    """Extract implicit preferences from user behavioral signals."""
    results = {"from_undos": 0, "from_corrections": 0, "from_edits": 0, "failed": 0}
    window = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    try:
        results["from_undos"] += await _process_undos(window)
    except Exception as exc:
        log.error("behavioral.undo_extraction_failed", error=str(exc))
        results["failed"] += 1

    try:
        results["from_corrections"] += await _process_corrections(window)
    except Exception as exc:
        log.error("behavioral.correction_extraction_failed", error=str(exc))
        results["failed"] += 1

    try:
        results["from_edits"] += await _process_draft_edits(window)
    except Exception as exc:
        log.error("behavioral.edit_extraction_failed", error=str(exc))
        results["failed"] += 1

    log.info("behavioral_signals.complete", **results)
    return results


async def _process_undos(window: datetime) -> int:
    """When user undoes an archive/label, reinforce 'always inbox' for that sender."""
    from core.models.email import Email

    count = 0
    async with get_db_session() as session:
        undone_result = await session.execute(
            select(MutationLedger)
            .where(
                MutationLedger.status == MutationStatus.UNDONE,
                MutationLedger.undone_at.isnot(None),
                MutationLedger.undone_at >= window,
            )
        )
        undone_mutations = undone_result.scalars().all()

        for mutation in undone_mutations:
            email = await session.get(Email, mutation.email_id)
            if not email or not email.from_address:
                continue

            # Check if we already have a behavioral memory for this sender
            existing = await session.execute(
                select(Memory).where(
                    Memory.user_id == mutation.user_id,
                    Memory.mailbox_id == mutation.mailbox_id,
                    Memory.source == "behavioral_signal",
                    Memory.structured_data["signal_type"].as_string() == "undo",
                    Memory.structured_data["sender"].as_string() == email.from_address,
                    Memory.is_active == True,  # noqa: E712
                )
            )
            if existing.scalar_one_or_none():
                # Reinforce existing memory
                mem = existing.scalar_one_or_none()
                if mem:
                    mem.confidence = min(1.0, mem.confidence + 0.1)
                    mem.last_reinforced_at = datetime.now(tz=timezone.utc)
                continue

            memory = Memory(
                id=uuid.uuid4(),
                user_id=mutation.user_id,
                mailbox_id=mutation.mailbox_id,
                scope=MemoryScope.MAILBOX_SPECIFIC,
                applies_to_all_mailboxes=False,
                memory_type=MemoryType.POLICY,
                content=f"User undid an automated action on email from {email.from_address}. Keep emails from this sender in inbox.",
                structured_data={
                    "rule": "always_inbox",
                    "targets": [email.from_address],
                    "signal_type": "undo",
                    "sender": email.from_address,
                },
                source="behavioral_signal",
                confidence=0.7,
                is_active=True,
                last_reinforced_at=datetime.now(tz=timezone.utc),
            )
            session.add(memory)
            count += 1

    return count


async def _process_corrections(window: datetime) -> int:
    """When user explicitly reclassifies a triage decision, create a policy memory."""
    count = 0
    async with get_db_session() as session:
        corrections = await session.execute(
            select(FeedbackEvent)
            .where(
                FeedbackEvent.feedback_type == "triage_correction",
                FeedbackEvent.processed == False,  # noqa: E712
                FeedbackEvent.created_at >= window,
            )
        )
        correction_events = corrections.scalars().all()

        for event in correction_events:
            intent = event.structured_intent or {}
            from_outcome = intent.get("from_outcome")
            to_outcome = intent.get("to_outcome")
            sender = intent.get("sender_address")

            if not (from_outcome and to_outcome and sender):
                continue

            memory = Memory(
                id=uuid.uuid4(),
                user_id=event.user_id,
                mailbox_id=event.mailbox_id,
                scope=MemoryScope.MAILBOX_SPECIFIC,
                applies_to_all_mailboxes=False,
                memory_type=MemoryType.POLICY,
                content=f"User corrected triage for {sender}: {from_outcome} → {to_outcome}",
                structured_data={
                    "rule": f"always_{to_outcome}" if to_outcome in ("inbox_keep", "brief_only") else "policy",
                    "targets": [sender],
                    "signal_type": "triage_correction",
                    "from_outcome": from_outcome,
                    "to_outcome": to_outcome,
                },
                source="behavioral_signal",
                confidence=0.85,
                is_active=True,
                last_reinforced_at=datetime.now(tz=timezone.utc),
            )
            session.add(memory)
            event.processed = True
            count += 1

    return count


async def _process_draft_edits(window: datetime) -> int:
    """When user heavily edits a draft, extract style signals."""
    count = 0
    async with get_db_session() as session:
        heavily_edited = await session.execute(
            select(Draft)
            .where(
                Draft.status == DraftStatus.EDITED_AND_SENT,
                Draft.edit_distance.isnot(None),
                Draft.edit_distance < 0.5,  # significant edits
                Draft.edits_tracked_at >= window,
            )
        )
        drafts = heavily_edited.scalars().all()

        for draft in drafts:
            if not draft.user_edited_text:
                continue

            # Check if style signal already exists for this draft
            existing = await session.execute(
                select(Memory).where(
                    Memory.source_feedback_id.is_(None),
                    Memory.structured_data["signal_type"].as_string() == "draft_edit",
                    Memory.structured_data["draft_id"].as_string() == str(draft.id),
                )
            )
            if existing.scalar_one_or_none():
                continue

            memory = Memory(
                id=uuid.uuid4(),
                user_id=draft.user_id,
                mailbox_id=draft.mailbox_id,
                scope=MemoryScope.MAILBOX_SPECIFIC,
                applies_to_all_mailboxes=False,
                memory_type=MemoryType.STYLE,
                content=f"User significantly edited a generated draft (similarity: {draft.edit_distance:.0%}). Their preferred version may indicate style preferences.",
                structured_data={
                    "signal_type": "draft_edit",
                    "draft_id": str(draft.id),
                    "edit_distance": draft.edit_distance,
                    "original_excerpt": draft.draft_text[:200],
                    "edited_excerpt": draft.user_edited_text[:200],
                },
                source="behavioral_signal",
                confidence=0.6,
                is_active=True,
                last_reinforced_at=datetime.now(tz=timezone.utc),
            )
            session.add(memory)
            count += 1

    return count
