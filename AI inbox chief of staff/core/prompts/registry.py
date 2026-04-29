"""
Prompt version registry — tracks prompt templates with versioning.
Enables A/B testing and rollback of prompt changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@dataclass
class PromptVersion:
    name: str
    version: str
    template: str
    created_at: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


class PromptRegistry:
    """In-memory prompt registry with versioning. Serializable to JSON for persistence."""

    def __init__(self) -> None:
        self._prompts: dict[str, dict[str, PromptVersion]] = {}
        self._active: dict[str, str] = {}

    def register(
        self, name: str, version: str, template: str, metadata: dict | None = None
    ) -> PromptVersion:
        content_hash = hashlib.sha256(template.encode()).hexdigest()[:12]
        pv = PromptVersion(
            name=name,
            version=version,
            template=template,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
            content_hash=content_hash,
            metadata=metadata or {},
        )
        self._prompts.setdefault(name, {})[version] = pv

        if name not in self._active:
            self._active[name] = version

        log.info("prompt.registered", name=name, version=version, hash=content_hash)
        return pv

    def get(self, name: str, version: str | None = None) -> PromptVersion | None:
        versions = self._prompts.get(name)
        if not versions:
            return None
        if version:
            return versions.get(version)
        active_version = self._active.get(name)
        return versions.get(active_version) if active_version else None

    def set_active(self, name: str, version: str) -> None:
        if name in self._prompts and version in self._prompts[name]:
            self._active[name] = version
            log.info("prompt.active_changed", name=name, version=version)

    def list_versions(self, name: str) -> list[PromptVersion]:
        return list(self._prompts.get(name, {}).values())

    def list_all(self) -> dict[str, list[str]]:
        return {name: list(versions.keys()) for name, versions in self._prompts.items()}

    def to_dict(self) -> dict:
        result = {}
        for name, versions in self._prompts.items():
            result[name] = {
                "active": self._active.get(name),
                "versions": {
                    v: {
                        "content_hash": pv.content_hash,
                        "created_at": pv.created_at,
                        "metadata": pv.metadata,
                    }
                    for v, pv in versions.items()
                },
            }
        return result


_registry = PromptRegistry()


def get_prompt_registry() -> PromptRegistry:
    return _registry


# Register default prompts
_registry.register(
    "triage_classifier",
    "v1",
    (
        "Classify the following email. Return JSON: "
        '{"outcome": "inbox_keep"|"brief_only"|"draft_candidate", '
        '"confidence": 0.0-1.0, "reason": "..."}'
    ),
)

_registry.register(
    "brief_summarizer",
    "v1",
    (
        "Summarize this email for a brief digest. "
        'Return JSON: {"category": "...", "summary": "...", "key_points": [...], "importance_score": 0.0-1.0}'
    ),
)

_registry.register(
    "draft_generator",
    "v1",
    (
        "Generate a concise, on-brand reply draft. "
        "Ground your reply ONLY in the email content provided. "
        'Return JSON: {"subject": "...", "body": "...", "grounding_confidence": 0.0-1.0}'
    ),
)

_registry.register(
    "policy_extractor",
    "v1",
    "Parse the user instruction and extract ALL policy rules as a JSON array.",
)

_registry.register(
    "memory_extractor",
    "v1",
    "Extract a persistent user preference or rule from this feedback.",
)
