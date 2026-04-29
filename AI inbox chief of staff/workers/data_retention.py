"""
Data retention — TTL-based purge of old records.
Retention periods:
  - Raw email content: 90 days
  - Triage decisions: 180 days
  - Audit events: 365 days
  - Expired mutation ledger entries: 30 days past undo window
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select, update

from core.db import get_db_session

log = structlog.get_logger(__name__)

RETENTION_EMAIL_CONTENT_DAYS = 90
RETENTION_TRIAGE_DAYS = 180
RETENTION_AUDIT_DAYS = 365
RETENTION_MUTATION_EXPIRED_DAYS = 30


async def run_data_retention() -> dict:
    """Purge old data according to retention policy."""
    results = {"emails_scrubbed": 0, "triage_deleted": 0, "audit_deleted": 0, "mutations_deleted": 0}
    now = datetime.now(tz=timezone.utc)

    async with get_db_session() as session:
        # Scrub raw email content (keep metadata, remove body)
        from core.models.email import Email

        email_cutoff = now - timedelta(days=RETENTION_EMAIL_CONTENT_DAYS)
        scrub_result = await session.execute(
            update(Email)
            .where(
                Email.received_at < email_cutoff,
                Email.body_text.isnot(None),
            )
            .values(body_text=None, body_html=None)
        )
        results["emails_scrubbed"] = scrub_result.rowcount

        # Delete old triage decisions
        from core.models.triage import TriageDecision

        triage_cutoff = now - timedelta(days=RETENTION_TRIAGE_DAYS)
        triage_result = await session.execute(
            delete(TriageDecision).where(TriageDecision.created_at < triage_cutoff)
        )
        results["triage_deleted"] = triage_result.rowcount

        # Delete old audit events
        from core.models.audit import AuditEvent

        audit_cutoff = now - timedelta(days=RETENTION_AUDIT_DAYS)
        audit_result = await session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < audit_cutoff)
        )
        results["audit_deleted"] = audit_result.rowcount

        # Delete expired mutation ledger entries past retention window
        from core.models.mutation_ledger import MutationLedger, MutationStatus

        mutation_cutoff = now - timedelta(days=RETENTION_MUTATION_EXPIRED_DAYS)
        mutation_result = await session.execute(
            delete(MutationLedger).where(
                MutationLedger.undo_expires_at < mutation_cutoff,
                MutationLedger.status.in_([MutationStatus.APPLIED, MutationStatus.EXPIRED]),
            )
        )
        results["mutations_deleted"] = mutation_result.rowcount

    log.info("data_retention.complete", **results)
    return results
