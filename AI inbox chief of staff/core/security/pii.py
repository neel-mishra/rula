"""
PII scrubbing for logs, traces, and error payloads.

Scrubs email addresses, phone numbers, SSNs, credit card numbers,
and OAuth tokens from structured log fields and string payloads.
"""

from __future__ import annotations

import re
from typing import Any

# ── Patterns ─────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
_TOKEN_RE = re.compile(r"(ya29\.[a-zA-Z0-9_\-]{20,})", re.IGNORECASE)  # Google OAuth access tokens
_REFRESH_TOKEN_RE = re.compile(r"(1//[a-zA-Z0-9_\-]{20,})", re.IGNORECASE)  # Google refresh tokens
_BEARER_RE = re.compile(r"(Bearer\s+)[a-zA-Z0-9._\-]+", re.IGNORECASE)
_API_KEY_RE = re.compile(r"(sk-[a-zA-Z0-9]{20,}|anthropic-[a-zA-Z0-9\-]+)", re.IGNORECASE)

_PATTERNS = [
    (_EMAIL_RE, "[EMAIL]"),
    (_PHONE_RE, "[PHONE]"),
    (_SSN_RE, "[SSN]"),
    (_CREDIT_CARD_RE, "[CARD]"),
    (_TOKEN_RE, "[OAUTH_TOKEN]"),
    (_REFRESH_TOKEN_RE, "[REFRESH_TOKEN]"),
    (_BEARER_RE, "Bearer [REDACTED]"),
    (_API_KEY_RE, "[API_KEY]"),
]

# Fields that should always be fully redacted (never partially matched)
_SENSITIVE_FIELD_NAMES = frozenset({
    "password",
    "secret",
    "token",
    "refresh_token",
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "encrypted_refresh_token",
    "encrypted_access_token",
    "token_encryption_key",
    "app_secret_key",
})


def scrub_string(text: str) -> str:
    """Redact PII patterns from a string."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub_dict(data: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """
    Recursively scrub PII from a dictionary (e.g., structured log event).
    Redacts sensitive field names entirely and scrubs string values.
    Max depth 10 to prevent infinite recursion on circular refs.
    """
    if depth > 10:
        return {"[TRUNCATED]": "max depth exceeded"}

    result = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_FIELD_NAMES:
            result[key] = "[REDACTED]"
        elif isinstance(value, str):
            result[key] = scrub_string(value)
        elif isinstance(value, dict):
            result[key] = scrub_dict(value, depth + 1)
        elif isinstance(value, list):
            result[key] = [
                scrub_dict(item, depth + 1) if isinstance(item, dict)
                else scrub_string(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def scrub_log_event(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    structlog processor that scrubs PII from all log events.
    Add to structlog pipeline via:
        structlog.configure(processors=[..., scrub_log_event, ...])
    """
    return scrub_dict(event_dict)
