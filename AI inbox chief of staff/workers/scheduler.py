"""
Scheduler worker — manages:
1. Gmail watch renewal per mailbox (daily, with jitter to avoid rate limits)
2. Brief scheduling (morning + afternoon windows per mailbox)
3. Nightly eval runs
4. Token refresh sweeps

Designed to run as a small Fargate task or invoked by EventBridge rules.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytz
import structlog

from core.config import settings
from core.db import get_db_session
from core.models.brief import Brief, BriefStatus, BriefWindow
from core.models.mailbox import Mailbox
from core.observability.tracing import init_tracing

log = structlog.get_logger(__name__)

# No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
init_tracing("inbox-cos-worker-scheduler")


# ─────────────────────────────────────────────────────────────────────────────
# Gmail Watch Renewal
# ─────────────────────────────────────────────────────────────────────────────

async def renew_gmail_watches() -> dict:
    """
    Renew Gmail push watch for all active mailboxes.
    Per-mailbox with jitter so N accounts don't hit the same second.
    Runs daily; renews watches expiring within 48 hours.
    """
    from sqlalchemy import select
    from core.gmail import GmailClient

    results = {"renewed": 0, "skipped": 0, "failed": 0}
    renewal_horizon = datetime.now(tz=timezone.utc) + timedelta(hours=48)

    async with get_db_session() as session:
        mailboxes_result = await session.execute(
            select(Mailbox).where(
                Mailbox.is_active == True,  # noqa: E712
                Mailbox.is_connected == True,  # noqa: E712
            )
        )
        mailboxes = mailboxes_result.scalars().all()

    for mailbox in mailboxes:
        # Only renew if expiring within 48h or no watch registered
        if mailbox.gmail_watch_expiration and mailbox.gmail_watch_expiration > renewal_horizon:
            results["skipped"] += 1
            continue

        # Jitter: 0-60s per mailbox to avoid Gmail rate limits
        jitter = random.uniform(0, 60)
        await asyncio.sleep(jitter)

        try:
            async with get_db_session() as session:
                mb = await session.get(Mailbox, mailbox.id)
                client = GmailClient(mb)
                watch_result = client.register_watch(topic_name=settings.gmail_webhook_topic)

                expiry_ms = watch_result.get("expiration")
                if expiry_ms:
                    mb.gmail_watch_expiration = datetime.fromtimestamp(
                        int(expiry_ms) / 1000, tz=timezone.utc
                    )
                mb.gmail_watch_resource_id = watch_result.get("resourceId")
                mb.gmail_history_id = str(watch_result.get("historyId", mb.gmail_history_id or ""))

            results["renewed"] += 1
            log.info(
                "scheduler.watch_renewed",
                mailbox_id=str(mailbox.id),
                gmail_email=mailbox.gmail_email,
                new_expiry=str(mb.gmail_watch_expiration),
            )
        except Exception as exc:
            results["failed"] += 1
            log.error(
                "scheduler.watch_renewal_failed",
                mailbox_id=str(mailbox.id),
                gmail_email=mailbox.gmail_email,
                error=str(exc),
            )

    log.info("scheduler.watch_renewal_complete", **results)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Brief Scheduling
# ─────────────────────────────────────────────────────────────────────────────

async def schedule_briefs() -> dict:
    """
    Check all active mailboxes and create Brief records for pending windows.
    Per-mailbox brief — no cross-mailbox unified brief mode.
    """
    from sqlalchemy import select, and_

    results = {"scheduled": 0, "skipped": 0}
    now = datetime.now(tz=timezone.utc)
    tz_obj = pytz.timezone(settings.brief_timezone)
    now_local = now.astimezone(tz_obj)
    current_hour = now_local.hour

    async with get_db_session() as session:
        mailboxes_result = await session.execute(
            select(Mailbox).where(
                Mailbox.is_active == True,  # noqa: E712
                Mailbox.brief_enabled == True,  # noqa: E712
            )
        )
        mailboxes = mailboxes_result.scalars().all()

    for mailbox in mailboxes:
        morning_hour = mailbox.brief_morning_hour or settings.brief_morning_hour
        afternoon_hour = mailbox.brief_afternoon_hour or settings.brief_afternoon_hour

        windows_to_check: list[tuple[BriefWindow, int]] = []
        if current_hour >= morning_hour and current_hour < afternoon_hour:
            windows_to_check.append((BriefWindow.MORNING, morning_hour))
        elif current_hour >= afternoon_hour:
            windows_to_check.append((BriefWindow.AFTERNOON, afternoon_hour))

        for window, hour in windows_to_check:
            scheduled_at = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
            scheduled_at_utc = scheduled_at.astimezone(timezone.utc)

            # Check if brief already exists for this window + mailbox + date
            async with get_db_session() as session:
                window_start = scheduled_at_utc - timedelta(hours=1)
                window_end = scheduled_at_utc + timedelta(hours=1)

                existing = await session.execute(
                    select(Brief).where(
                        Brief.mailbox_id == mailbox.id,
                        Brief.window == window,
                        Brief.scheduled_at >= window_start,
                        Brief.scheduled_at <= window_end,
                    )
                )
                if existing.scalar_one_or_none():
                    results["skipped"] += 1
                    continue

                # Determine time window for email collection
                if window == BriefWindow.MORNING:
                    collect_start = (scheduled_at - timedelta(hours=12)).astimezone(timezone.utc)
                else:
                    collect_start = now_local.replace(hour=morning_hour, minute=0).astimezone(timezone.utc)

                brief = Brief(
                    id=uuid.uuid4(),
                    mailbox_id=mailbox.id,
                    user_id=mailbox.user_id,
                    window=window,
                    scheduled_at=scheduled_at_utc,
                    status=BriefStatus.PENDING,
                    policy_version="v1",
                    correlation_id=str(uuid.uuid4()),
                )
                session.add(brief)

                results["scheduled"] += 1
                log.info(
                    "scheduler.brief_created",
                    mailbox_id=str(mailbox.id),
                    window=window.value,
                    scheduled_at=str(scheduled_at_utc),
                )

                # Dispatch to brief queue
                await _dispatch_brief_job(
                    brief_id=brief.id,
                    mailbox_id=mailbox.id,
                    user_id=mailbox.user_id,
                    window=window.value,
                    time_window_start=collect_start,
                    time_window_end=scheduled_at_utc,
                    correlation_id=brief.correlation_id,
                )

    log.info("scheduler.brief_scheduling_complete", **results)
    return results


async def _dispatch_brief_job(
    brief_id, mailbox_id, user_id, window, time_window_start, time_window_end, correlation_id
) -> None:
    """Push brief job to the configured queue backend."""
    from core.queue import get_queue_backend

    backend = get_queue_backend()
    await backend.send(
        "brief",
        {
            "brief_id": str(brief_id),
            "mailbox_id": str(mailbox_id),
            "user_id": str(user_id),
            "window": window,
            "time_window_start": time_window_start.isoformat(),
            "time_window_end": time_window_end.isoformat(),
            "correlation_id": correlation_id,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint — run all scheduled tasks
# ─────────────────────────────────────────────────────────────────────────────

async def run_all_scheduled_tasks() -> None:
    """Main scheduler entrypoint. Run all due tasks sequentially."""
    log.info("scheduler.started")
    await renew_gmail_watches()
    await schedule_briefs()

    # Token refresh sweep — proactively refresh OAuth tokens nearing expiry
    try:
        await _refresh_expiring_tokens()
    except Exception as exc:
        log.error("scheduler.token_refresh_failed", error=str(exc))

    # Draft edit tracking — detect user modifications to generated drafts
    try:
        from workers.draft_tracker import run_draft_edit_tracking
        await run_draft_edit_tracking()
    except Exception as exc:
        log.error("scheduler.draft_tracker_failed", error=str(exc))

    # Memory confidence decay — deactivate expired/decayed memories
    try:
        from workers.memory_decay import run_memory_decay
        await run_memory_decay()
    except Exception as exc:
        log.error("scheduler.memory_decay_failed", error=str(exc))

    # Behavioral signal extraction — observe user actions and extract implicit preferences
    try:
        from workers.behavioral_signals import run_behavioral_signal_extraction
        await run_behavioral_signal_extraction()
    except Exception as exc:
        log.error("scheduler.behavioral_signals_failed", error=str(exc))

    # Style extraction — weekly refresh of voice profiles (runs but skips if recent)
    try:
        from workers.style_extraction import run_style_extraction
        await run_style_extraction()
    except Exception as exc:
        log.error("scheduler.style_extraction_failed", error=str(exc))

    # Nightly eval — run evaluation suite across all active mailboxes
    try:
        from workers.nightly_eval import run_nightly_evals
        await run_nightly_evals()
    except Exception as exc:
        log.error("scheduler.nightly_eval_failed", error=str(exc))

    # Data retention — purge old records per retention policy
    try:
        from workers.data_retention import run_data_retention
        await run_data_retention()
    except Exception as exc:
        log.error("scheduler.data_retention_failed", error=str(exc))

    log.info("scheduler.completed")


async def _refresh_expiring_tokens() -> dict:
    """Proactively refresh OAuth tokens nearing expiry."""
    from sqlalchemy import select
    from core.gmail.auth import refresh_token_if_needed

    results = {"refreshed": 0, "skipped": 0, "failed": 0}
    async with get_db_session() as session:
        mailboxes_result = await session.execute(
            select(Mailbox).where(
                Mailbox.is_active == True,  # noqa: E712
                Mailbox.is_connected == True,  # noqa: E712
                Mailbox.encrypted_refresh_token.isnot(None),
            )
        )
        for mailbox in mailboxes_result.scalars().all():
            try:
                refreshed = await refresh_token_if_needed(mailbox)
                if refreshed:
                    results["refreshed"] += 1
                else:
                    results["skipped"] += 1
            except Exception:
                results["failed"] += 1

    log.info("scheduler.token_refresh_complete", **results)
    return results


if __name__ == "__main__":
    asyncio.run(run_all_scheduled_tasks())
