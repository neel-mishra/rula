from __future__ import annotations
import base64
import json
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.gmail_client import GmailClient
from app.ingestion.normalizer import normalize_message, validate_normalized_message
from app.core.security import decrypt_token
from app.repositories.user_repo import UserRepository
from app.repositories.message_repo import MessageRepository

logger = structlog.get_logger()


def parse_gmail_notification(payload: dict) -> str | None:
    """
    Extract the Gmail historyId from a Cloud Pub/Sub push notification.
    Pub/Sub wraps the data as base64-encoded JSON in payload["message"]["data"].
    Returns historyId string, or None if parsing fails.
    """
    try:
        encoded = payload["message"]["data"]
        decoded = base64.urlsafe_b64decode(encoded + "==").decode("utf-8")
        data = json.loads(decoded)
        return str(data.get("historyId", ""))
    except (KeyError, ValueError, Exception) as e:
        logger.warning("Failed to parse Gmail notification", error=str(e))
        return None


async def handle_new_message(
    gmail_message_id: str,
    user_id: str,
    db: AsyncSession,
) -> None:
    """
    Full ingestion pipeline for a single Gmail message.
    1. Fetch user + decrypt refresh token
    2. Fetch raw Gmail message
    3. Normalize + validate
    4. Deduplicate (skip if already ingested)
    5. Persist Message record
    6. Create WorkflowRun (state: INGESTED)
    7. Enqueue orchestrator task
    """
    user_repo = UserRepository(db)
    msg_repo = MessageRepository(db)

    # 1. Get user and credentials
    from sqlalchemy import select
    from app.models.user import User
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("User not found for ingestion", user_id=user_id)
        return

    refresh_token = decrypt_token(user.google_refresh_token)

    # 2. Fetch raw message
    gmail = GmailClient(refresh_token)
    raw = gmail.get_message(gmail_message_id)

    # 3. Normalize + validate
    normalized = normalize_message(raw)
    validate_normalized_message(normalized)

    # 4. Deduplicate
    existing = await msg_repo.get_by_gmail_id(gmail_message_id, user_id)
    if existing:
        logger.info("Message already ingested, skipping", gmail_message_id=gmail_message_id)
        return

    # 5. Persist Message
    message = await msg_repo.create(
        user_id=user_id,
        gmail_message_id=normalized.message_id,
        gmail_thread_id=normalized.thread_id,
        subject=normalized.subject,
        sender_email=normalized.sender_email,
        sender_name=normalized.sender_name,
        received_at=normalized.received_at,
        body_preview=normalized.body_preview,
        ingest_status="normalized",
    )

    # 6. Create WorkflowRun
    from app.models.message import WorkflowRun
    workflow_run = WorkflowRun(
        message_id=message.id,
        user_id=user_id,
        state="ingested",
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)

    logger.info(
        "Message ingested, workflow created",
        message_id=str(message.id),
        workflow_run_id=str(workflow_run.id),
    )

    # 7. Run orchestrator inline (Cloud Tasks in production — ICE-P1-003)
    from app.orchestrator.state_machine import WorkflowStateMachine, WorkflowState
    fsm = WorkflowStateMachine(str(workflow_run.id), WorkflowState.INGESTED)
    await fsm.transition(WorkflowState.NORMALIZED, db)
    await fsm.dispatch_agents(db)
