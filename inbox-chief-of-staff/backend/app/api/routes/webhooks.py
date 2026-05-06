from __future__ import annotations
import base64
import json
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import decrypt_token
from app.ingestion.gmail_client import GmailClient
from app.ingestion.webhook_handler import parse_gmail_notification, handle_new_message
from app.repositories.user_repo import UserRepository

logger = structlog.get_logger()
router = APIRouter()


def _parse_email_from_notification(payload: dict) -> str | None:
    """Extract the emailAddress field from a Pub/Sub push notification payload."""
    try:
        encoded = payload["message"]["data"]
        decoded = base64.urlsafe_b64decode(encoded + "==").decode("utf-8")
        data = json.loads(decoded)
        return data.get("emailAddress") or None
    except Exception:
        return None


@router.post("/gmail")
async def gmail_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Receive Gmail Pub/Sub push notifications.
    Parse the historyId, look up new messages via the History API, and run the
    full ingestion pipeline for each newly arrived message.
    """
    payload = await request.json()
    history_id = parse_gmail_notification(payload)

    if not history_id:
        return {"status": "ignored"}

    # Extract the email address from the notification so we can look up the user.
    email = _parse_email_from_notification(payload)
    if not email:
        logger.warning("Gmail webhook: could not extract emailAddress from notification")
        return {"status": "ignored"}

    # Look up the user in the database.
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(email)
    if not user:
        logger.warning("Gmail webhook: no user found for email", email=email)
        return {"status": "ignored"}

    if not user.google_refresh_token:
        logger.warning("Gmail webhook: user has no refresh token", user_id=str(user.id))
        return {"status": "ignored"}

    logger.info(
        "Gmail webhook received — listing history",
        history_id=history_id,
        email=email,
        user_id=str(user.id),
    )

    # Use the History API to find messages added since the given historyId.
    refresh_token = decrypt_token(user.google_refresh_token)
    gmail = GmailClient(refresh_token)
    try:
        history_response = (
            gmail._service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=history_id,
                historyTypes=["messageAdded"],
            )
            .execute()
        )
    except Exception as exc:
        logger.error("Gmail webhook: history list failed", error=str(exc))
        # Acknowledge to Pub/Sub to avoid redelivery loops on permanent errors.
        return {"status": "error", "detail": str(exc)}

    new_message_ids: list[str] = []
    for record in history_response.get("history", []):
        for added in record.get("messagesAdded", []):
            msg_id = added.get("message", {}).get("id")
            if msg_id:
                new_message_ids.append(msg_id)

    if not new_message_ids:
        logger.info("Gmail webhook: no new messages in history", history_id=history_id)
        return {"status": "accepted", "new_messages": 0}

    # Enqueue each message for the full ingestion pipeline as a background task
    # so we return quickly to Pub/Sub before the 30-second ack deadline.
    user_id = str(user.id)
    for msg_id in new_message_ids:
        background_tasks.add_task(handle_new_message, msg_id, user_id, db)

    logger.info(
        "Gmail webhook: enqueued messages for ingestion",
        count=len(new_message_ids),
        history_id=history_id,
    )
    return {"status": "accepted", "new_messages": len(new_message_ids)}
