"""
IngestionAgent — Gmail watch event handling, history sync, canonical email parsing.
Strictly mailbox-scoped: every operation uses the mailbox's own Gmail credentials.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

import structlog
from sqlalchemy import select

from core.db import get_db_session
from core.gmail import GmailClient
from core.models.email import Email
from core.models.mailbox import Mailbox
from core.schemas.contracts import IngestionResult, IngestionTask
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)

_DOMAIN_RE = re.compile(r"@([\w.-]+)$")


def _extract_domain(address: str) -> str | None:
    m = _DOMAIN_RE.search(address.lower())
    return m.group(1) if m else None


def _parse_headers(headers: list[dict]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in headers}


def _build_features(raw_msg: dict, headers: dict) -> dict[str, Any]:
    """Compute lightweight email features without LLM."""
    label_ids = raw_msg.get("labelIds", [])
    to_raw = headers.get("to", "").lower()
    cc_raw = headers.get("cc", "").lower()
    # Direct-to-user: single recipient, no CC (high signal for personal email)
    to_count = len([a for a in to_raw.split(",") if a.strip()])
    is_direct = to_count == 1 and not cc_raw.strip()
    return {
        "is_reply": bool(headers.get("in-reply-to")),
        "is_unread": "UNREAD" in label_ids,
        "is_inbox": "INBOX" in label_ids,
        "is_sent": "SENT" in label_ids,
        "has_list_unsubscribe": bool(headers.get("list-unsubscribe")),
        "has_list_id": bool(headers.get("list-id")),
        "is_newsletter": bool(headers.get("list-unsubscribe") or headers.get("list-id")),
        "is_direct_to_user": is_direct,
        "precedence": headers.get("precedence", ""),
        "x_mailer": headers.get("x-mailer", ""),
    }


def _extract_plain_body(payload: dict) -> str | None:
    """Recursively extract plain-text body from Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        import base64
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_plain_body(part)
        if result:
            return result
    return None


class IngestionAgent(BaseAgent[IngestionTask, IngestionResult]):
    name = "ingestion_agent"

    async def _execute(self, task: IngestionTask) -> IngestionResult:
        async with get_db_session() as session:
            # Load mailbox — enforces mailbox isolation
            mailbox = await session.get(Mailbox, task.mailbox_id)
            if not mailbox or not mailbox.is_active:
                raise ValueError(f"Mailbox {task.mailbox_id} not found or inactive")

            if mailbox.user_id != task.user_id:
                raise PermissionError("Mailbox does not belong to user — isolation violation")

            # Idempotency check
            existing = await session.execute(
                select(Email).where(
                    Email.mailbox_id == task.mailbox_id,
                    Email.gmail_message_id == task.gmail_message_id,
                )
            )
            if existing.scalar_one_or_none():
                log.info(
                    "ingestion.duplicate",
                    gmail_message_id=task.gmail_message_id,
                    correlation_id=task.correlation_id,
                )
                return IngestionResult(
                    email_id=uuid.uuid4(),  # placeholder; caller can query by gmail_message_id
                    gmail_message_id=task.gmail_message_id,
                    is_duplicate=True,
                )

            # Fetch from Gmail using mailbox credentials
            client = GmailClient(mailbox)
            raw_msg = client.get_message(task.gmail_message_id, format="full")

            # Parse headers
            payload = raw_msg.get("payload", {})
            headers = _parse_headers(payload.get("headers", []))

            from_raw = headers.get("from", "")
            from_name, from_address = parseaddr(from_raw)
            from_domain = _extract_domain(from_address) if from_address else None

            to_raw = headers.get("to", "")
            to_addresses = [a.strip() for a in to_raw.split(",") if a.strip()]

            cc_raw = headers.get("cc", "")
            cc_addresses = [a.strip() for a in cc_raw.split(",") if a.strip()]

            # Parse received timestamp
            date_str = headers.get("date")
            received_at: datetime | None = None
            if date_str:
                try:
                    received_at = parsedate_to_datetime(date_str).astimezone(timezone.utc)
                except Exception:
                    received_at = None

            body_text = _extract_plain_body(payload)
            snippet = raw_msg.get("snippet", "")
            label_ids = raw_msg.get("labelIds", [])
            features = _build_features(raw_msg, headers)

            # Extract attachment text (best-effort; failures do not block ingestion)
            attachment_extracts: list[dict] = []
            try:
                from core.email.attachments import extract_gmail_payload_attachments

                def _fetch_attachment(att_id: str) -> bytes:
                    return client.get_attachment(task.gmail_message_id, att_id)

                extracts = extract_gmail_payload_attachments(payload, _fetch_attachment)
                attachment_extracts = [e.to_dict() for e in extracts]
                if attachment_extracts:
                    features["attachment_count"] = len(attachment_extracts)
                    features["attachment_has_text"] = any(
                        e["extracted_text"] for e in attachment_extracts
                    )
            except Exception as att_exc:
                log.debug("ingestion.attachment_extract_skipped", error=str(att_exc))

            # Compute sender reputation from historical patterns
            try:
                from core.gmail.reputation import compute_sender_reputation

                reputation = await compute_sender_reputation(
                    mailbox_id=task.mailbox_id,
                    sender_address=from_address or "",
                    sender_domain=from_domain or "",
                    session=session,
                )
                features["sender_vip"] = reputation.is_vip
                features["sender_frequent"] = reputation.is_frequent
                features["sender_reputation_score"] = reputation.score
                features["sender_reply_rate"] = reputation.reply_rate
                features["sender_total_received"] = reputation.total_received
            except Exception as rep_exc:
                log.debug("ingestion.reputation_skipped", error=str(rep_exc))

            email = Email(
                id=uuid.uuid4(),
                mailbox_id=task.mailbox_id,
                user_id=task.user_id,
                gmail_message_id=task.gmail_message_id,
                gmail_thread_id=raw_msg.get("threadId", ""),
                subject=headers.get("subject"),
                from_address=from_address or None,
                from_name=from_name or None,
                from_domain=from_domain,
                to_addresses=to_addresses,
                cc_addresses=cc_addresses,
                reply_to=headers.get("reply-to"),
                snippet=snippet,
                body_text=body_text,
                gmail_labels=label_ids,
                received_at=received_at,
                features=features,
                attachment_extracts=attachment_extracts,
            )
            # Generate embedding for RAG retrieval
            try:
                from core.llm.embeddings import generate_embedding

                embed_text = f"{email.subject or ''} {email.from_address or ''} {email.snippet or ''}"
                embed_text = embed_text[:2000]  # truncate for API limits
                embedding_vector = await generate_embedding(embed_text)
                if hasattr(Email, "embedding") and Email.embedding is not None:
                    email.embedding = embedding_vector
            except Exception as emb_exc:
                log.debug("ingestion.embedding_skipped", error=str(emb_exc))

            session.add(email)

            # Update mailbox history_id for next sync
            new_history_id = raw_msg.get("historyId")
            if new_history_id:
                mailbox.gmail_history_id = str(new_history_id)

            await session.flush()

            log.info(
                "ingestion.email_stored",
                email_id=str(email.id),
                gmail_message_id=task.gmail_message_id,
                from_domain=from_domain,
                is_newsletter=features.get("is_newsletter"),
                correlation_id=task.correlation_id,
            )

            return IngestionResult(
                email_id=email.id,
                gmail_message_id=task.gmail_message_id,
                is_duplicate=False,
                features_extracted=True,
            )
