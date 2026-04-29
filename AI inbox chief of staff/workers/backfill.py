"""
Initial backfill worker — runs after a new mailbox is connected.
Fetches the last N days of email from Gmail and ingests them
through the standard orchestrator pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog

from core.config import settings

log = structlog.get_logger(__name__)

# Default: backfill the last 7 days on first connect
_DEFAULT_BACKFILL_DAYS = 7
_DEFAULT_MAX_MESSAGES = 200


async def backfill_mailbox(
    user_id: uuid.UUID,
    mailbox_id: uuid.UUID,
    days: int = _DEFAULT_BACKFILL_DAYS,
    max_messages: int = _DEFAULT_MAX_MESSAGES,
) -> dict:
    """
    Fetch recent messages from Gmail and ingest through the pipeline.
    Idempotent: duplicates are caught by the (mailbox_id, gmail_message_id) unique constraint.
    """
    from core.db import get_db_session
    from core.models.mailbox import Mailbox
    from core.gmail import GmailClient
    from orchestrator.orchestrator import Orchestrator

    async with get_db_session() as session:
        mailbox = await session.get(Mailbox, mailbox_id)
        if not mailbox or not mailbox.is_connected:
            return {"error": "Mailbox not found or not connected"}

    gmail = GmailClient(mailbox)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    query = f"after:{cutoff.strftime('%Y/%m/%d')}"

    log.info(
        "backfill.started",
        mailbox_id=str(mailbox_id),
        query=query,
        max_messages=max_messages,
    )

    # Fetch message IDs from Gmail
    message_ids: list[str] = []
    page_token: str | None = None
    while len(message_ids) < max_messages:
        result = gmail.list_messages(
            query=query,
            max_results=min(50, max_messages - len(message_ids)),
            page_token=page_token,
        )
        messages = result.get("messages", [])
        if not messages:
            break
        message_ids.extend(m["id"] for m in messages)
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    log.info("backfill.messages_found", count=len(message_ids), mailbox_id=str(mailbox_id))

    # Process through orchestrator (shadow mode respected automatically)
    orchestrator = Orchestrator()
    processed = 0
    duplicates = 0
    errors = 0

    for msg_id in message_ids:
        try:
            result = await orchestrator.process_new_email(
                user_id=user_id,
                mailbox_id=mailbox_id,
                gmail_message_id=msg_id,
                gmail_history_id="",
                correlation_id=str(uuid.uuid4()),
            )
            if result.get("ok"):
                if result.get("stopped_at") == "ingestion" and result.get("reason") == "duplicate":
                    duplicates += 1
                else:
                    processed += 1
            else:
                errors += 1
        except Exception as exc:
            errors += 1
            log.warning("backfill.message_error", msg_id=msg_id, error=str(exc))

    summary = {
        "mailbox_id": str(mailbox_id),
        "messages_found": len(message_ids),
        "processed": processed,
        "duplicates": duplicates,
        "errors": errors,
    }
    log.info("backfill.completed", **summary)
    return summary
