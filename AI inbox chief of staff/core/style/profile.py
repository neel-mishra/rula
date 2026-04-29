"""
Style profile extraction — analyzes sent mail corpus to build per-mailbox writing style.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from core.config import settings
from core.db import get_db_session

log = structlog.get_logger(__name__)


@dataclass
class StyleProfile:
    tone: str
    formality_level: int  # 1 (casual) to 5 (formal)
    avg_sentence_length: str  # "short" | "medium" | "long"
    greeting_style: str
    closing_style: str
    vocabulary_traits: list[str]
    sample_phrases: list[str]
    generated_at: str


async def extract_style_profile(mailbox_id: uuid.UUID, session: Any) -> StyleProfile | None:
    """Analyze sent emails from this mailbox to extract writing style."""
    from core.models.email import Email
    from core.llm.client import get_llm_client
    from core.security.injection import get_system_prompt_preamble

    result = await session.execute(
        select(Email)
        .where(
            Email.mailbox_id == mailbox_id,
            Email.features["is_sent"].as_boolean() == True,  # noqa: E712
        )
        .order_by(Email.received_at.desc())
        .limit(50)
    )
    sent_emails = result.scalars().all()

    if len(sent_emails) < 5:
        log.info("style.insufficient_samples", mailbox_id=str(mailbox_id), count=len(sent_emails))
        return None

    samples = []
    for email in sent_emails[:30]:
        body = (email.body_text or email.snippet or "")[:500]
        if body.strip():
            samples.append(body)

    if len(samples) < 3:
        return None

    corpus = "\n---\n".join(samples[:20])

    llm = get_llm_client()
    system_prompt = (
        get_system_prompt_preamble()
        + "\n\nAnalyze the writing style from these sent emails. "
        + "Return JSON: {\n"
        + '  "tone": "friendly|professional|casual|direct|warm",\n'
        + '  "formality_level": 1-5,\n'
        + '  "avg_sentence_length": "short|medium|long",\n'
        + '  "greeting_style": "typical greeting pattern",\n'
        + '  "closing_style": "typical sign-off pattern",\n'
        + '  "vocabulary_traits": ["trait1", "trait2"],\n'
        + '  "sample_phrases": ["phrase they commonly use"]\n'
        + "}\n"
    )

    response = await llm.complete(
        system=system_prompt,
        user=f"Sent email samples:\n{corpus}",
        max_tokens=500,
        temperature=0.2,
        response_format="json",
        mailbox_id=str(mailbox_id),
    )

    parsed = json.loads(response.content)
    return StyleProfile(
        tone=parsed.get("tone", "professional"),
        formality_level=parsed.get("formality_level", 3),
        avg_sentence_length=parsed.get("avg_sentence_length", "medium"),
        greeting_style=parsed.get("greeting_style", ""),
        closing_style=parsed.get("closing_style", ""),
        vocabulary_traits=parsed.get("vocabulary_traits", []),
        sample_phrases=parsed.get("sample_phrases", []),
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
    )


async def get_or_refresh_style_profile(
    mailbox_id: uuid.UUID, session: Any, force_refresh: bool = False
) -> StyleProfile | None:
    """Load cached profile from mailbox feature_flags, or extract fresh."""
    from core.models.mailbox import Mailbox

    mailbox = await session.get(Mailbox, mailbox_id)
    if not mailbox:
        return None

    cached = mailbox.feature_flags.get("style_profile")
    if cached and not force_refresh:
        try:
            return StyleProfile(**cached)
        except (TypeError, KeyError):
            pass

    profile = await extract_style_profile(mailbox_id, session)
    if profile:
        flags = dict(mailbox.feature_flags)
        flags["style_profile"] = asdict(profile)
        mailbox.feature_flags = flags

    return profile
