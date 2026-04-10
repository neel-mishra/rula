from __future__ import annotations

import re
from typing import Any

_MAX_EVIDENCE_CHARS = 32_000
_MAX_STR_FIELD = 4_000

# Keys (and key substrings) never persisted in DLQ/incident *context* blobs.
_REDACT_PLACEHOLDER = "[REDACTED]"
_SENSITIVE_KEY_NAMES: frozenset[str] = frozenset(
    {
        "prompt",
        "system_prompt",
        "user_prompt",
        "messages",
        "api_key",
        "anthropic_api_key",
        "google_api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "bearer",
        "cookie",
        "set-cookie",
    }
)
_SECRET_KEY_SUBSTRINGS = re.compile(
    r"(secret|password|token|api_key|apikey|bearer|credential|authorization)",
    re.IGNORECASE,
)


def _strip_controls(s: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def sanitize_evidence_text(text: str) -> str:
    t = _strip_controls(text).strip()
    if len(t) > _MAX_EVIDENCE_CHARS:
        t = t[:_MAX_EVIDENCE_CHARS]
    return t


def sanitize_evidence_id(evidence_id: str) -> str:
    s = _strip_controls(evidence_id).strip()[:128]
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    s = s.replace("..", "_")
    return s or "unknown"


def sanitize_account_payload(payload: dict) -> dict:
    """Shallow copy with bounded string fields and control-char removal."""
    out = dict(payload)
    for key in ("company", "industry", "health_plan", "notes"):
        if key in out and isinstance(out[key], str):
            v = _strip_controls(out[key])[:_MAX_STR_FIELD]
            out[key] = v
    if "contact" in out and isinstance(out["contact"], dict):
        c = dict(out["contact"])
        for ck in ("name", "title"):
            if ck in c and isinstance(c[ck], str):
                c[ck] = _strip_controls(c[ck])[:500]
        out["contact"] = c
    return out


def _is_sensitive_key(key: str) -> bool:
    lk = key.lower()
    if lk in _SENSITIVE_KEY_NAMES:
        return True
    return bool(_SECRET_KEY_SUBSTRINGS.search(key))


def redact_context_for_persistence(obj: Any, *, max_depth: int = 32) -> Any:
    """Recursively redact sensitive keys from structures prior to DLQ/incident persistence."""

    def _walk(node: Any, depth: int) -> Any:
        if depth > max_depth:
            return _REDACT_PLACEHOLDER
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for k, v in node.items():
                if _is_sensitive_key(str(k)):
                    out[str(k)] = _REDACT_PLACEHOLDER
                else:
                    out[str(k)] = _walk(v, depth + 1)
            return out
        if isinstance(node, (list, tuple)):
            seq = [_walk(x, depth + 1) for x in node]
            return type(node)(seq) if isinstance(node, tuple) else seq
        return node

    return _walk(obj, 0)
