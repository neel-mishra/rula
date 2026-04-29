"""
Style extraction worker — periodically analyzes sent emails to build per-mailbox voice profiles.
Runs weekly via scheduler.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select

from core.db import get_db_session
from core.models.mailbox import Mailbox

log = structlog.get_logger(__name__)


async def run_style_extraction() -> dict:
    """Extract or refresh writing style profiles for all active mailboxes."""
    from core.style.profile import get_or_refresh_style_profile

    results = {"extracted": 0, "skipped": 0, "failed": 0}

    async with get_db_session() as session:
        mailboxes_result = await session.execute(
            select(Mailbox).where(
                Mailbox.is_active == True,  # noqa: E712
                Mailbox.is_connected == True,  # noqa: E712
                Mailbox.draft_enabled == True,  # noqa: E712
            )
        )
        mailboxes = mailboxes_result.scalars().all()

        for mailbox in mailboxes:
            try:
                profile = await get_or_refresh_style_profile(
                    mailbox.id, session, force_refresh=True
                )
                if profile:
                    results["extracted"] += 1
                    log.info("style.extracted", mailbox_id=str(mailbox.id), tone=profile.tone)
                else:
                    results["skipped"] += 1
            except Exception as exc:
                results["failed"] += 1
                log.error("style.extraction_failed", mailbox_id=str(mailbox.id), error=str(exc))

    log.info("style_extraction.complete", **results)
    return results
