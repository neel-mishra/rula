"""
DLQ replay worker — replays failed messages from dead-letter queues
back to their source queues for reprocessing.

Supports selective replay (by time range, mailbox, or all) and
dry-run mode. Idempotent: messages already processed are skipped
by the existing deduplication in the ingest pipeline.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import boto3
import structlog

from core.config import settings

log = structlog.get_logger(__name__)

# DLQ → source queue mapping
_DLQ_TO_SOURCE = {
    "ingest-dlq": settings.sqs_ingest_queue_url,
    "triage-dlq": settings.sqs_triage_queue_url,
    "draft-dlq": settings.sqs_draft_queue_url,
    "brief-dlq": settings.sqs_brief_queue_url,
    "memory-dlq": settings.sqs_memory_queue_url,
    "eval-dlq": settings.sqs_eval_queue_url,
}


def replay_dlq(
    dlq_url: str,
    source_queue_url: str,
    max_messages: int = 100,
    dry_run: bool = False,
    mailbox_filter: str | None = None,
) -> dict[str, Any]:
    """
    Replay messages from a DLQ back to the source queue.

    Args:
        dlq_url: SQS DLQ URL to read from
        source_queue_url: SQS source queue URL to send to
        max_messages: Maximum number of messages to replay
        dry_run: If True, read and inspect but don't re-send
        mailbox_filter: If set, only replay messages for this mailbox_id

    Returns:
        Summary of replay operation
    """
    if not dlq_url or not source_queue_url:
        return {"error": "Queue URLs not configured"}

    sqs = boto3.client("sqs", region_name=settings.aws_region)
    replayed = 0
    skipped = 0
    errors = 0
    inspected = []

    while replayed + skipped < max_messages:
        response = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=min(10, max_messages - replayed - skipped),
            WaitTimeSeconds=1,
            AttributeNames=["All"],
        )
        messages = response.get("Messages", [])
        if not messages:
            break

        for msg in messages:
            try:
                body = json.loads(msg["Body"])
            except (json.JSONDecodeError, KeyError):
                body = {}

            msg_mailbox = body.get("mailbox_id", "")

            # Apply mailbox filter
            if mailbox_filter and msg_mailbox != mailbox_filter:
                skipped += 1
                continue

            inspected.append({
                "message_id": msg["MessageId"],
                "mailbox_id": msg_mailbox,
                "correlation_id": body.get("correlation_id", ""),
                "approximate_receive_count": msg.get("Attributes", {}).get(
                    "ApproximateReceiveCount", "?"
                ),
            })

            if dry_run:
                skipped += 1
                continue

            try:
                # Re-send to source queue
                send_kwargs: dict = {
                    "QueueUrl": source_queue_url,
                    "MessageBody": msg["Body"],
                }
                # Preserve FIFO attributes if present
                if msg_mailbox:
                    send_kwargs["MessageGroupId"] = msg_mailbox
                    send_kwargs["MessageDeduplicationId"] = (
                        f"replay-{msg['MessageId']}-{int(time.time())}"
                    )

                sqs.send_message(**send_kwargs)

                # Delete from DLQ after successful replay
                sqs.delete_message(
                    QueueUrl=dlq_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
                replayed += 1

                log.info(
                    "dlq.replay.sent",
                    message_id=msg["MessageId"],
                    mailbox_id=msg_mailbox,
                    source_queue=source_queue_url,
                )

            except Exception as exc:
                errors += 1
                log.error(
                    "dlq.replay.error",
                    message_id=msg["MessageId"],
                    error=str(exc),
                )

    summary = {
        "replayed": replayed,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "inspected": inspected if dry_run else [],
    }
    log.info("dlq.replay.complete", **{k: v for k, v in summary.items() if k != "inspected"})
    if errors > 0 and not dry_run:
        try:
            from core.alerts import Severity, emit_alert
            emit_alert(
                Severity.WARNING,
                f"DLQ replay had {errors} error(s)",
                {
                    "dlq_url": dlq_url,
                    "source_queue_url": source_queue_url,
                    "replayed": replayed,
                    "skipped": skipped,
                    "errors": errors,
                },
            )
        except Exception as exc:
            log.warning("dlq.replay.alert_failed", error=str(exc))
    return summary


def replay_all_dlqs(dry_run: bool = False, mailbox_filter: str | None = None) -> dict:
    """Replay all configured DLQs."""
    results = {}
    for dlq_name, source_url in _DLQ_TO_SOURCE.items():
        dlq_url = getattr(settings, f"sqs_{dlq_name.replace('-', '_')}_url", "")
        if dlq_url and source_url:
            results[dlq_name] = replay_dlq(
                dlq_url=dlq_url,
                source_queue_url=source_url,
                dry_run=dry_run,
                mailbox_filter=mailbox_filter,
            )
    return results
