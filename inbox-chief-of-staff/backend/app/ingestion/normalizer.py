from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from app.ingestion.gmail_client import GmailClient


@dataclass
class NormalizedMessage:
    message_id: str
    thread_id: str
    subject: str
    sender_email: str
    sender_name: str
    received_at: datetime
    body_preview: str          # max 500 chars of plain text
    has_attachments: bool
    label_ids: list[str]


def normalize_message(raw_message: dict[str, Any]) -> NormalizedMessage:
    """Parse a raw Gmail API message dict into a NormalizedMessage."""
    payload = raw_message.get("payload", {})
    headers = payload.get("headers", [])

    def header(name: str) -> str:
        for h in headers:
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    # Sender
    from_header = header("From")
    sender_name, sender_email = parseaddr(from_header)
    if not sender_email:
        sender_email = from_header.strip()

    # Date
    date_str = header("Date")
    try:
        received_at = parsedate_to_datetime(date_str)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
    except Exception:
        # Fall back to internalDate (ms since epoch)
        ts_ms = int(raw_message.get("internalDate", 0))
        received_at = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)

    # Body
    body_text = GmailClient.decode_body(payload)
    # Strip excess whitespace, truncate
    body_text = re.sub(r"\s+", " ", body_text).strip()
    body_preview = body_text[:500]

    # Attachments — any non-text/plain, non-text/html part with a filename
    has_attachments = any(
        p.get("filename") for p in payload.get("parts", []) if p.get("filename")
    )

    return NormalizedMessage(
        message_id=raw_message["id"],
        thread_id=raw_message.get("threadId", ""),
        subject=header("Subject"),
        sender_email=sender_email.lower().strip(),
        sender_name=sender_name or sender_email,
        received_at=received_at,
        body_preview=body_preview,
        has_attachments=has_attachments,
        label_ids=raw_message.get("labelIds", []),
    )


def validate_normalized_message(msg: NormalizedMessage) -> None:
    """Raise ValueError if any required field is missing or malformed."""
    if not msg.message_id:
        raise ValueError("message_id is required")
    if not msg.sender_email:
        raise ValueError("sender_email is required")
    if len(msg.body_preview) > 500:
        raise ValueError("body_preview must be ≤ 500 chars")
