"""PII scrub + redaction for gold-eval samples.

Wraps the project-wide scrubber (`core/security/pii.py`) and adds
gold-specific operations:
- Sender display name -> `Person_<sha1[:8]>` keyed per mailbox salt.
- Signature truncation on `-- \\n` boundary or last-N-line heuristic.
- Attachment extracted text run through scrub_string.
- URL querystring stripping for tokenish params.
- Quoted reply chain truncated to immediate parent.

scrub_email_for_gold is idempotent and deterministic given (email, salt).
"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from core.security.pii import scrub_dict, scrub_string

SCRUB_VERSION = "v1"

_SIGNATURE_DELIM = re.compile(r"^\s*--\s*$", re.MULTILINE)
_QUOTE_PREFIX = re.compile(r"^>+ ?", re.MULTILINE)
_REPLY_HEADER = re.compile(
    r"^On .+ wrote:$|^From:.+|^-----\s*Original Message\s*-----$",
    re.MULTILINE,
)
_TOKENISH_PARAMS = (
    "token", "auth", "key", "secret", "session",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "mc_eid", "mc_cid",
)


def _hash_name(display_name: str, mailbox_salt: str) -> str:
    if not display_name:
        return ""
    h = hashlib.sha1(f"{mailbox_salt}::{display_name.lower()}".encode("utf-8")).hexdigest()
    return f"Person_{h[:8]}"


def _truncate_signature(text: str) -> str:
    parts = _SIGNATURE_DELIM.split(text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].rstrip()
    return text


def _truncate_quoted_chain(text: str) -> str:
    """Drop everything from the first reply-header forward."""
    m = _REPLY_HEADER.search(text)
    if m:
        text = text[: m.start()].rstrip()
    text = _QUOTE_PREFIX.sub("", text)
    return text


def _strip_url_tokens(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                if k.lower() not in _TOKENISH_PARAMS]
        return urlunparse(parsed._replace(query=urlencode(kept)))
    except Exception:
        return url


_URL_RE = re.compile(r"https?://[^\s)>\]]+")


def _scrub_urls(text: str) -> str:
    return _URL_RE.sub(lambda m: _strip_url_tokens(m.group(0)), text)


def _scrub_body(text: str) -> str:
    text = _truncate_signature(text)
    text = _truncate_quoted_chain(text)
    text = _scrub_urls(text)
    return scrub_string(text)


def scrub_email_for_gold(
    email: dict[str, Any],
    mailbox_salt: str,
) -> dict[str, Any]:
    """Return a redacted copy of `email` safe to persist as a gold sample."""
    if not mailbox_salt:
        raise ValueError("mailbox_salt is required for deterministic name hashing")
    out = deepcopy(email)

    if "from_name" in out:
        out["from_name"] = _hash_name(out.get("from_name") or "", mailbox_salt)

    for body_field in ("body_text", "snippet", "body_html"):
        if out.get(body_field):
            out[body_field] = _scrub_body(out[body_field])

    if "subject" in out and out["subject"]:
        out["subject"] = scrub_string(re.sub(r"\s+", " ", out["subject"]).strip())

    extracts = out.get("attachment_extracts") or []
    if isinstance(extracts, list):
        out["attachment_extracts"] = [
            {**(ae if isinstance(ae, dict) else {}),
             "text": scrub_string((ae or {}).get("text") or "")[:5000]}
            for ae in extracts
        ]

    # scrub_dict catches any other PII-like fields (emails, phones, tokens).
    return scrub_dict(out)
