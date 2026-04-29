"""
Ingest worker — queue consumer for Gmail push notifications.
Runs the full Orchestrator pipeline per message.
Handles retries and per-mailbox isolation.
"""

from __future__ import annotations

import asyncio
import signal
import uuid

import structlog

from core.config import settings
from core.observability.tracing import init_tracing
from core.queue import QueueMessage

log = structlog.get_logger(__name__)

# No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
init_tracing("inbox-cos-worker-ingest")

_RUNNING = True


def _shutdown(signum, frame) -> None:
    global _RUNNING
    log.info("worker.shutdown_signal", signum=signum)
    _RUNNING = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)


async def process_message(message: QueueMessage) -> None:
    """Process a single queue message through the orchestrator pipeline."""
    import json

    body = json.loads(message.body)

    user_id = uuid.UUID(body["user_id"])
    mailbox_id = uuid.UUID(body["mailbox_id"])
    history_id = body["history_id"]
    last_history_id = body.get("last_history_id", history_id)
    correlation_id = body.get("correlation_id", str(uuid.uuid4()))

    bound_log = log.bind(
        correlation_id=correlation_id,
        mailbox_id=str(mailbox_id),
        history_id=history_id,
    )

    bound_log.info("worker.processing_message")

    # Fetch new messages via history delta
    from core.db import get_db_session
    from core.mailbox import get_mailbox_backend
    from core.models.mailbox import Mailbox
    from orchestrator import Orchestrator

    async with get_db_session() as session:
        mailbox = await session.get(Mailbox, mailbox_id)
        if not mailbox or not mailbox.is_active:
            bound_log.warning("worker.mailbox_not_found_or_inactive")
            return

        mailbox_backend = get_mailbox_backend(mailbox)
        try:
            history_result = mailbox_backend.get_history(start_history_id=last_history_id)
        except Exception as exc:
            bound_log.error("worker.history_fetch_failed", error=str(exc))
            raise

        messages_added = []
        for h in history_result.get("history", []):
            for msg in h.get("messagesAdded", []):
                messages_added.append(msg.get("message", {}).get("id"))

    orch = Orchestrator()
    for message_id in messages_added:
        if not message_id:
            continue
        try:
            result = await orch.process_new_email(
                user_id=user_id,
                mailbox_id=mailbox_id,
                gmail_message_id=message_id,
                gmail_history_id=history_id,
                correlation_id=f"{correlation_id}-{message_id}",
            )
            bound_log.info(
                "worker.message_processed",
                gmail_message_id=message_id,
                outcome=result.get("triage", {}).get("outcome"),
            )
        except Exception as exc:
            bound_log.error("worker.message_failed", gmail_message_id=message_id, error=str(exc))
            raise  # Let SQS retry handle it


async def poll_loop() -> None:
    """Main queue poll loop."""
    from core.queue import get_queue_backend

    backend = get_queue_backend()
    log.info("worker.started", queue_backend=settings.queue_backend, queue_name="ingest")

    while _RUNNING:
        try:
            messages = await backend.receive(
                "ingest",
                max_messages=10,
                wait_time_seconds=20,
                visibility_timeout=300,
            )

            for message in messages:
                try:
                    await process_message(message)
                    # Delete on success
                    await backend.delete("ingest", message.receipt_handle)
                except Exception as exc:
                    log.error("worker.message_error", error=str(exc))
                    # Leave in queue for retry; backend-specific redelivery handles retries

        except Exception as exc:
            log.error("worker.poll_error", error=str(exc))
            await asyncio.sleep(5)

    log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(poll_loop())
