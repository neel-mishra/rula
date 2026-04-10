from __future__ import annotations

"""Append-only JSONL telemetry for local prototype runs.

**Metadata policy:** ``TelemetryEvent.metadata`` must not carry secrets, raw prompts,
or other high-sensitivity strings.

- Top-level and **nested** dict keys matching :data:`FORBIDDEN_METADATA_KEYS` or
  containing obvious secret substrings are **omitted** before persistence.
- Dicts and lists are walked up to :data:`_METADATA_MAX_DEPTH` levels; deeper nesting
  is replaced with a placeholder to avoid runaway payloads.
- String values are truncated to :data:`_METADATA_MAX_STRING_LEN` characters.
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

EVENTS_FILE = Path("telemetry_events.jsonl")

# Keys never written to disk (lowercased for comparison).
FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
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
    }
)

_SECRET_SUBSTRINGS = re.compile(
    r"(secret|password|token|api_key|apikey|bearer|credential)",
    re.IGNORECASE,
)

_METADATA_MAX_DEPTH = 10
_METADATA_MAX_STRING_LEN = 800


def _is_forbidden_key(key: str) -> bool:
    lk = key.lower()
    if lk in FORBIDDEN_METADATA_KEYS:
        return True
    return bool(_SECRET_SUBSTRINGS.search(key))


def _sanitize_metadata_value(obj: object, depth: int) -> object:
    if depth > _METADATA_MAX_DEPTH:
        return "[REDACTED_DEPTH]"
    if isinstance(obj, dict):
        out: dict[str, object] = {}
        for key, value in obj.items():
            sk = str(key)
            if _is_forbidden_key(sk):
                logger.debug("Telemetry metadata omitted nested key %r (policy)", key)
                continue
            out[sk] = _sanitize_metadata_value(value, depth + 1)
        return out
    if isinstance(obj, list):
        return [_sanitize_metadata_value(v, depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return [_sanitize_metadata_value(v, depth + 1) for v in obj]
    if isinstance(obj, str) and len(obj) > _METADATA_MAX_STRING_LEN:
        return obj[:_METADATA_MAX_STRING_LEN] + "…"
    return obj


def _sanitize_metadata(meta: dict) -> dict:
    if not meta:
        return {}
    return _sanitize_metadata_value(dict(meta), 0)  # type: ignore[return-value]


@dataclass
class TelemetryEvent:
    event_type: str
    pipeline: str
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    provider: str = ""
    fallback_used: bool = False
    success: bool = True
    error: str = ""
    metadata: dict = field(default_factory=dict)


def emit(event: TelemetryEvent) -> None:
    try:
        payload = asdict(event)
        payload["metadata"] = _sanitize_metadata(dict(event.metadata))
        with EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception as e:
        logger.warning("Telemetry emit failed: %s", e)


def read_events(limit: int = 200) -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    lines = EVENTS_FILE.read_text(encoding="utf-8").strip().splitlines()
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
