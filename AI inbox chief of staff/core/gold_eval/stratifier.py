"""Stratum classifier for inbox samples.

Pure functions: given an email dict (Gmail-shaped or our canonical
Email-shape dict), assign a stratum. Heuristics mirror the rule
signals already used by TriageAgent so the gold dataset captures the
same boundary cases.
"""

from __future__ import annotations

import re
from typing import Any

from core.models.gold_sample import GoldStratum

_NEWSLETTER_HEADERS = ("list-unsubscribe", "list-id", "list-post")
_TRANSACTIONAL_LOCALPARTS = (
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications", "alerts", "billing", "receipts",
    "support", "info", "hello",
)
_CALENDAR_DOMAINS = ("calendar.google.com", "outlook.office365.com")
_CALENDAR_MIME = ("text/calendar", "application/ics")
_QUESTION_RE = re.compile(r"\?\s*$|\?\s")
_IMPERATIVE_VERBS = (
    "please", "could you", "can you", "would you", "let me know",
    "review", "approve", "sign", "respond", "confirm",
)


def _headers_lower(email: dict[str, Any]) -> dict[str, str]:
    """Flatten Gmail header list into a lowercase-keyed dict."""
    payload = email.get("payload") or {}
    raw_headers = payload.get("headers") or email.get("headers") or []
    out: dict[str, str] = {}
    for h in raw_headers:
        name = (h.get("name") or "").lower()
        if name:
            out[name] = h.get("value") or ""
    return out


def _from_local(headers: dict[str, str]) -> str:
    sender = headers.get("from", "")
    m = re.search(r"<?([^@<>\s]+)@", sender)
    return (m.group(1) if m else "").lower()


def _has_calendar_attachment(email: dict[str, Any]) -> bool:
    payload = email.get("payload") or {}
    parts = payload.get("parts") or []
    for p in parts:
        if (p.get("mimeType") or "").lower() in _CALENDAR_MIME:
            return True
        if p.get("filename", "").lower().endswith(".ics"):
            return True
    return False


def _user_in_to(headers: dict[str, str], user_email: str | None) -> bool:
    if not user_email:
        return False
    to_field = headers.get("to", "").lower()
    return user_email.lower() in to_field


def _body_text(email: dict[str, Any]) -> str:
    return (email.get("snippet") or email.get("body_text") or "")[:2000]


def classify_stratum(
    email: dict[str, Any],
    user_email: str | None = None,
) -> GoldStratum:
    """Assign a stratum. First match wins; order encodes precedence."""
    headers = _headers_lower(email)

    if any(h in headers for h in _NEWSLETTER_HEADERS):
        return GoldStratum.NEWSLETTER

    sender_local = _from_local(headers)
    sender_domain = headers.get("from", "").split("@")[-1].rstrip(">").lower()

    if sender_domain in _CALENDAR_DOMAINS or _has_calendar_attachment(email):
        return GoldStratum.CALENDAR

    in_reply_to = headers.get("in-reply-to") or email.get("parent_message_id")
    if in_reply_to and _user_in_to(headers, user_email):
        return GoldStratum.DIRECT_REPLY

    if any(local in sender_local for local in _TRANSACTIONAL_LOCALPARTS):
        return GoldStratum.UPDATE

    body = _body_text(email).lower()
    has_question = bool(_QUESTION_RE.search(body))
    has_imperative = any(verb in body for verb in _IMPERATIVE_VERBS)
    if (has_question or has_imperative) and "list-unsubscribe" not in headers:
        return GoldStratum.ACTION_REQUIRED

    return GoldStratum.AMBIGUOUS
