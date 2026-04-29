"""
Draft edit tracker — observes how users modify generated drafts before sending.
Captures edit distance to feed style refinement.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from core.db import get_db_session
from core.models.draft import Draft, DraftStatus
from core.models.email import Email
from core.models.mailbox import Mailbox

log = structlog.get_logger(__name__)


def _compute_edit_distance(original: str, edited: str) -> float:
    """Normalized similarity ratio: 1.0 = identical, 0.0 = completely different."""
    return difflib.SequenceMatcher(None, original, edited).ratio()


async def run_draft_edit_tracking() -> dict:
    """Check generated drafts for user edits by comparing with sent messages."""
    results = {"tracked": 0, "no_send": 0, "failed": 0}
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    async with get_db_session() as session:
        drafts_result = await session.execute(
            select(Draft)
            .where(
                Draft.status == DraftStatus.GENERATED,
                Draft.gmail_draft_id.isnot(None),
                Draft.user_edited_text.is_(None),
                Draft.created_at >= cutoff,
            )
            .limit(100)
        )
        drafts = drafts_result.scalars().all()

        for draft in drafts:
            try:
                email = await session.get(Email, draft.email_id)
                if not email:
                    continue

                mailbox = await session.get(Mailbox, draft.mailbox_id)
                if not mailbox or not mailbox.is_connected:
                    continue

                # Check if user sent a message in this thread after the draft was created
                sent_result = await session.execute(
                    select(Email)
                    .where(
                        Email.mailbox_id == draft.mailbox_id,
                        Email.gmail_thread_id == email.gmail_thread_id,
                        Email.features["is_sent"].as_boolean() == True,  # noqa: E712
                        Email.received_at >= draft.created_at,
                    )
                    .order_by(Email.received_at.asc())
                    .limit(1)
                )
                sent_email = sent_result.scalar_one_or_none()

                if not sent_email:
                    results["no_send"] += 1
                    continue

                sent_text = sent_email.body_text or sent_email.snippet or ""
                edit_dist = _compute_edit_distance(draft.draft_text, sent_text)

                draft.user_edited_text = sent_text
                draft.edit_distance = edit_dist
                draft.edits_tracked_at = datetime.now(tz=timezone.utc)

                if edit_dist > 0.9:
                    draft.status = DraftStatus.ACCEPTED
                else:
                    draft.status = DraftStatus.EDITED_AND_SENT

                results["tracked"] += 1
                log.info(
                    "draft_tracker.tracked",
                    draft_id=str(draft.id),
                    edit_distance=round(edit_dist, 3),
                    status=draft.status.value,
                )

            except Exception as exc:
                results["failed"] += 1
                log.error("draft_tracker.failed", draft_id=str(draft.id), error=str(exc))

    log.info("draft_tracker.complete", **results)
    return results
