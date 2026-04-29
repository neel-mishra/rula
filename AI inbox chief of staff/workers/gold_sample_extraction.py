"""Gold-eval sample extraction worker.

Admin-triggered. Reads a real Gmail inbox, classifies into strata,
scrubs PII, persists `GoldSample` rows. The Gmail-read code path is
clearly marked DEFERRED — it activates only when both
`settings.gold_sampling_enabled=True` AND OAuth credentials are
present on the target mailbox.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from core.config import settings
from core.db import get_db_session
from core.gold_eval.sampler import DEFAULT_TARGETS, stratified_sample
from core.gold_eval.scrubber import SCRUB_VERSION, scrub_email_for_gold
from core.gold_eval.stratifier import classify_stratum
from core.models.gold_sample import GoldFixtureType, GoldSample, GoldStratum
from core.models.mailbox import Mailbox

log = structlog.get_logger(__name__)


# Per-stratum Gmail search queries used to bias the candidate pool toward
# each label's natural population. Combined with classify_stratum to
# double-check that the label fits.
_GMAIL_QUERY_BY_STRATUM: dict[GoldStratum, str] = {
    GoldStratum.NEWSLETTER: "list:* OR has:list-unsubscribe newer_than:90d",
    GoldStratum.DIRECT_REPLY: "in:anywhere -category:promotions newer_than:90d",
    GoldStratum.UPDATE: "from:noreply OR from:notifications newer_than:90d",
    GoldStratum.ACTION_REQUIRED: "is:unread newer_than:90d",
    GoldStratum.CALENDAR: "filename:ics OR from:calendar.google.com newer_than:90d",
    GoldStratum.AMBIGUOUS: "newer_than:90d -category:promotions",
}


async def extract_gold_samples(
    *,
    mailbox_id: uuid.UUID,
    dry_run: bool = True,
    fixture_types: list[GoldFixtureType] | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Top-level entrypoint. Returns a summary dict; persists rows when
    dry_run=False AND settings.gold_sampling_enabled=True.
    """
    fixture_types = fixture_types or [
        GoldFixtureType.TRIAGE,
        GoldFixtureType.DRAFT,
        GoldFixtureType.BRIEF,
        GoldFixtureType.MEMORY,
    ]

    if not settings.gold_sampling_enabled:
        log.info(
            "gold_extraction.deferred",
            reason="gold_sampling_enabled=False",
            mailbox_id=str(mailbox_id),
        )
        return {
            "status": "deferred",
            "reason": "gold_sampling_enabled=False",
            "mailbox_id": str(mailbox_id),
            "samples_persisted": 0,
        }

    async with get_db_session() as session:
        mailbox = await session.get(Mailbox, mailbox_id)
        if not mailbox or not mailbox.is_connected:
            return {
                "status": "skipped",
                "reason": "mailbox not connected",
                "mailbox_id": str(mailbox_id),
                "samples_persisted": 0,
            }

    # === DEFERRED: activates post-OAuth ===========================
    # Everything below this fence performs live Gmail reads. The
    # function returns early above when the feature flag is off, so
    # this code does not execute today. When the flag flips to True
    # in production, the flow is:
    #   1. instantiate GmailClient with the mailbox creds
    #   2. for each stratum, run list_messages with the biased query
    #   3. fetch full message via get_message(format="full")
    #   4. classify with stratifier (defense in depth)
    #   5. scrub via scrub_email_for_gold(salt=settings.gold_sample_name_hash_salt)
    #   6. persist GoldSample rows with consented_at=now() and is_active=True
    # ==============================================================
    candidates = await _fetch_candidates(mailbox_id)
    classified_buckets = stratified_sample(
        candidates=candidates,
        classifier=classify_stratum,
        seed=seed,
    )

    persisted = 0
    if not dry_run:
        async with get_db_session() as session:
            for stratum, samples in classified_buckets.items():
                for raw in samples:
                    scrubbed = scrub_email_for_gold(
                        raw, mailbox_salt=settings.gold_sample_name_hash_salt
                    )
                    for fixture_type in fixture_types:
                        session.add(
                            GoldSample(
                                id=uuid.uuid4(),
                                mailbox_id=mailbox_id,
                                user_id=mailbox.user_id,
                                fixture_type=fixture_type,
                                stratum=stratum,
                                source_gmail_message_id=raw.get("id"),
                                raw_payload=raw,
                                scrubbed_payload=scrubbed,
                                scrub_version=SCRUB_VERSION,
                                consented_at=datetime.now(tz=timezone.utc),
                                is_active=True,
                            )
                        )
                        persisted += 1

    return {
        "status": "ok" if not dry_run else "dry_run",
        "mailbox_id": str(mailbox_id),
        "candidates_seen": len(candidates),
        "samples_persisted": persisted,
        "per_stratum": {s.value: len(v) for s, v in classified_buckets.items()},
    }


async def _fetch_candidates(mailbox_id: uuid.UUID) -> list[dict[str, Any]]:
    """
    DEFERRED: fetches real Gmail messages for the mailbox. Until
    `gold_sampling_enabled` flips, callers short-circuit before
    reaching this function (see the early return above).
    """
    from core.gmail.client import GmailClient

    candidates: list[dict[str, Any]] = []
    async with get_db_session() as session:
        mailbox = await session.get(Mailbox, mailbox_id)
        if not mailbox:
            return candidates
        client = GmailClient(mailbox)
        for stratum, query in _GMAIL_QUERY_BY_STRATUM.items():
            listing = client.list_messages(query=query, max_results=100)
            for stub in listing.get("messages", []) or []:
                msg = client.get_message(stub["id"], format="full")
                candidates.append(msg)
    return candidates
