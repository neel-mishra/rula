"""
Gmail push webhook endpoint.
Resolves mailbox from notification, dispatches to ingest queue.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_db, get_db_session
from core.models.mailbox import Mailbox

router = APIRouter()
log = structlog.get_logger(__name__)


class GmailPushNotification(BaseModel):
    message: dict
    subscription: str


@router.post("/gmail")
async def gmail_push(request: Request) -> dict:
    """
    Receive Gmail push notification from Google Pub/Sub.
    Validates HMAC signature, resolves mailbox, dispatches ingestion task.
    """
    body = await request.body()

    # Validate webhook signature (Google Pub/Sub HMAC or Bearer token)
    if settings.gmail_webhook_secret:
        # Check for Pub/Sub push token (Authorization header)
        auth_header = request.headers.get("Authorization", "")
        expected_token = f"Bearer {settings.gmail_webhook_secret}"
        if auth_header and auth_header != expected_token:
            log.warning("webhook.invalid_auth_token")
            raise HTTPException(status_code=403, detail="Invalid authorization token")

        # Fallback: HMAC signature check
        if not auth_header:
            sig = request.headers.get("X-Goog-Signature", "")
            expected = hmac.new(
                settings.gmail_webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(sig, expected):
                log.warning("webhook.invalid_signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Decode Pub/Sub message
    message = payload.get("message", {})
    data_b64 = message.get("data", "")
    if not data_b64:
        return {"status": "no_data"}

    try:
        decoded_data = base64.b64decode(data_b64, validate=True)
        notification = json.loads(decoded_data.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Cannot decode notification data")

    email_address = notification.get("emailAddress")
    history_id = str(notification.get("historyId", ""))

    if not email_address:
        return {"status": "missing_email_address"}

    # Resolve mailbox by gmail email — always per-mailbox, never cross-mailbox
    async with get_db_session() as session:
        result = await session.execute(
            select(Mailbox).where(
                Mailbox.gmail_email == email_address,
                Mailbox.is_active == True,  # noqa: E712
            )
        )
        mailbox = result.scalar_one_or_none()

        if not mailbox:
            log.warning("webhook.mailbox_not_found", email=email_address)
            return {"status": "mailbox_not_found"}

        user_id = mailbox.user_id
        mailbox_id = mailbox.id
        last_history_id = mailbox.gmail_history_id or history_id

    correlation_id = str(uuid.uuid4())

    # Dispatch to SQS ingest queue
    await _dispatch_ingest_job(
        user_id=user_id,
        mailbox_id=mailbox_id,
        history_id=history_id,
        last_history_id=last_history_id,
        correlation_id=correlation_id,
    )

    log.info(
        "webhook.dispatched",
        email_address=email_address,
        mailbox_id=str(mailbox_id),
        history_id=history_id,
        correlation_id=correlation_id,
    )
    return {"status": "accepted", "correlation_id": correlation_id}


@router.post("/ses-inbound")
async def ses_inbound(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    Receive an inbound email via SNS-wrapped SES notification and route it
    into the assistant pipeline.

    Envelope shape (SNS → SES):
        { "Type": "Notification", "Message": "<json-encoded SES payload>" }

    SES payload shape:
        { "notificationType": "Received",
          "mail": { "source": "<sender>", "commonHeaders": {...} },
          "content": "<base64 RFC822>" (optional) }

    Security: if `settings.ses_inbound_secret` is set, requires matching
    Authorization bearer token. Otherwise permissive (dev/test).
    """
    from email import policy
    from email.parser import BytesParser

    from core.models.assistant_conversation import (
        AssistantConversation,
        AssistantMessage,
    )
    from core.models.feedback import FeedbackEvent
    from core.models.user import User
    from core.schemas.contracts import PolicyCompileTask
    from subagents.policy import PolicyAgent

    body = await request.body()

    # Auth
    if getattr(settings, "ses_inbound_secret", None):
        expected = f"Bearer {settings.ses_inbound_secret}"
        if request.headers.get("Authorization", "") != expected:
            log.warning("ses_inbound.invalid_auth")
            raise HTTPException(status_code=403, detail="Invalid authorization")

    try:
        envelope = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Unwrap SNS envelope if present
    if envelope.get("Type") == "Notification":
        try:
            ses_payload = json.loads(envelope["Message"])
        except (KeyError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Malformed SNS Message")
    else:
        ses_payload = envelope

    mail = ses_payload.get("mail", {})
    sender = (mail.get("source") or "").strip().lower()
    common_headers = mail.get("commonHeaders", {})
    subject = common_headers.get("subject", "") or ""
    if not sender:
        from_list = common_headers.get("from") or []
        if from_list:
            from email.utils import parseaddr
            _, sender = parseaddr(from_list[0])
            sender = sender.lower()

    if not sender:
        raise HTTPException(status_code=400, detail="Could not determine sender")

    # Decode raw MIME body if SES action was SNS-with-content
    instruction_body = subject
    raw_content_b64 = ses_payload.get("content")
    if raw_content_b64:
        try:
            raw_bytes = base64.b64decode(raw_content_b64)
            msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        instruction_body = payload.decode(
                            part.get_content_charset() or "utf-8",
                            errors="replace",
                        ).strip()
                        break
        except Exception as parse_exc:
            log.warning("ses_inbound.mime_parse_failed", error=str(parse_exc))

    if not instruction_body:
        raise HTTPException(status_code=400, detail="Empty instruction")

    correlation_id = str(uuid.uuid4())

    user_result = await session.execute(
        select(User).where(User.email == sender, User.is_active == True)  # noqa: E712
    )
    user = user_result.scalar_one_or_none()
    if not user:
        log.info("ses_inbound.unknown_sender", sender=sender)
        return {"status": "unknown_sender"}

    # Start a new conversation per inbound email (no threading for now)
    conversation = AssistantConversation(
        id=uuid.uuid4(),
        user_id=user.id,
        mailbox_id=None,
        title=(subject or instruction_body)[:80] or "Email instruction",
    )
    session.add(conversation)
    await session.flush()

    feedback = FeedbackEvent(
        id=uuid.uuid4(),
        user_id=user.id,
        mailbox_id=None,
        feedback_type="assistant_instruction",
        raw_content=instruction_body,
        structured_intent={
            "conversation_id": str(conversation.id),
            "channel": "ses_inbound",
            "sender": sender,
        },
        processed=False,
        correlation_id=correlation_id,
    )
    session.add(feedback)
    await session.flush()

    user_message = AssistantMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="user",
        content=instruction_body,
        response_data={"channel": "ses_inbound"},
        feedback_event_id=feedback.id,
    )
    session.add(user_message)

    # Compile policy rules
    agent = PolicyAgent()
    task = PolicyCompileTask(
        user_id=user.id,
        mailbox_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        correlation_id=correlation_id,
        policy_version="v1",
        instruction_text=instruction_body,
        source="ses_inbound",
    )
    response = await agent.run(task)
    payload = response.payload
    rules_created = payload.rules_created if payload else 0
    needs_clarification = bool(payload and payload.needs_clarification)
    clarification_question = payload.clarification_question if payload else None

    if needs_clarification:
        assistant_text = clarification_question or "Could you clarify?"
    else:
        assistant_text = (
            f"Got it — created {rules_created} rule(s) from your email instruction."
        )

    assistant_message = AssistantMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_text,
        response_data={
            "rules_created": rules_created,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "feedback_event_id": str(feedback.id),
            "channel": "ses_inbound",
        },
        feedback_event_id=feedback.id,
    )
    session.add(assistant_message)

    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    conversation.last_message_at = now
    conversation.message_count = 2
    await session.flush()

    log.info(
        "ses_inbound.processed",
        sender=sender,
        rules_created=rules_created,
        correlation_id=correlation_id,
    )
    return {
        "status": "accepted",
        "correlation_id": correlation_id,
        "conversation_id": str(conversation.id),
        "rules_created": rules_created,
        "needs_clarification": needs_clarification,
    }


async def _dispatch_ingest_job(
    user_id: uuid.UUID,
    mailbox_id: uuid.UUID,
    history_id: str,
    last_history_id: str,
    correlation_id: str,
) -> None:
    """Push ingestion job to the configured queue backend."""
    from core.queue import get_queue_backend

    try:
        backend = get_queue_backend()
        await backend.send(
            "ingest",
            {
                "user_id": str(user_id),
                "mailbox_id": str(mailbox_id),
                "history_id": history_id,
                "last_history_id": last_history_id,
                "correlation_id": correlation_id,
            },
            group_id=str(mailbox_id),  # FIFO ordering by mailbox (SQS path)
            dedup_id=f"{mailbox_id}-{history_id}",
        )
    except Exception as exc:
        log.error("webhook.queue_dispatch_failed", error=str(exc), correlation_id=correlation_id)
        raise
