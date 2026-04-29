"""
DraftAgent — voice-aligned reply draft generation.
Writes drafts to Gmail Drafts only. Never sends.
Applies skills/writing-style.md as required writing policy.
Includes grounding checks and hallucination minimization.
"""

from __future__ import annotations

import uuid

import structlog

from core.config import settings
from core.schemas.contracts import DraftResult, DraftTask
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Writing style policy — loaded once at module import
# ─────────────────────────────────────────────────────────────────────────────

def _load_writing_style() -> str:
    """Load skills/writing-style.md. Raises if not found — content pipelines require it."""
    import os
    # Path relative to repo root
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "skills", "writing-style.md"),
        "/Users/neelmishra/.cursor/Rula/skills/writing-style.md",
    ]
    for path in candidates:
        normalized = os.path.normpath(path)
        if os.path.exists(normalized):
            with open(normalized, "r") as f:
                return f.read()
    raise FileNotFoundError(
        "skills/writing-style.md not found. "
        "Content-generation pipelines require this file. "
        "Per plan: block production until writing-style policy injection is confirmed."
    )


_WRITING_STYLE: str = _load_writing_style()


class DraftAgent(BaseAgent[DraftTask, DraftResult]):
    name = "draft_agent"

    def _check_kill_switches(self, task: DraftTask) -> bool:
        if settings.kill_switch_llm:
            return True
        return False

    async def _execute(self, task: DraftTask) -> DraftResult:
        from sqlalchemy import select
        from core.db import get_db_session
        from core.llm.client import get_llm_client
        from core.mailbox import get_mailbox_backend
        from core.models.draft import Draft, DraftStatus
        from core.models.email import Email
        from core.models.mailbox import Mailbox
        from core.models.memory import Memory, MemoryScope, MemoryType
        from core.prompts.experiments import resolve_variant
        from core.prompts.registry import get_prompt_registry
        from core.security.injection import get_system_prompt_preamble, sanitize_for_llm

        async with get_db_session() as session:
            email = await session.get(Email, task.email_id)
            if not email or email.mailbox_id != task.mailbox_id:
                raise ValueError(f"Email {task.email_id} not found or mailbox mismatch")

            mailbox = await session.get(Mailbox, task.mailbox_id)
            if not mailbox:
                raise ValueError(f"Mailbox {task.mailbox_id} not found")

            # Resolve A/B variant for this mailbox (if any active experiment)
            variant = await resolve_variant("draft_generator", task.mailbox_id, session)
            prompt_version = variant.prompt_version if variant else "v1"
            registered = get_prompt_registry().get("draft_generator", prompt_version)
            task_directive = registered.template if registered else (
                "Generate a concise, on-brand reply draft. "
                "Ground your reply ONLY in the email content provided. "
                'Return JSON: {"subject": "...", "body": "...", "grounding_confidence": 0.0-1.0}'
            )

            # Load style memories for this mailbox
            style_mems = await session.execute(
                select(Memory).where(
                    Memory.user_id == task.user_id,
                    Memory.memory_type == MemoryType.STYLE,
                    Memory.is_active == True,  # noqa: E712
                    (Memory.mailbox_id == task.mailbox_id) | (Memory.applies_to_all_mailboxes == True),  # noqa: E712
                )
            )
            style_instructions = [m.content for m in style_mems.scalars().all()]

            # Load thread context (up to 5 prior messages for multi-turn context)
            thread_messages = []
            if email.gmail_thread_id:
                thread_result = await session.execute(
                    select(Email)
                    .where(
                        Email.mailbox_id == task.mailbox_id,
                        Email.gmail_thread_id == email.gmail_thread_id,
                        Email.id != email.id,
                    )
                    .order_by(Email.received_at.desc())
                    .limit(5)
                )
                thread_messages = list(reversed(thread_result.scalars().all()))

            # Sanitize untrusted content
            sanitized_subject, blocked_s = sanitize_for_llm(email.subject or "", "subject")
            sanitized_body, blocked_b = sanitize_for_llm(email.body_text or email.snippet or "", "email")

            if blocked_s or blocked_b:
                raise ValueError("Draft blocked: injection detected in email content")

            # Load extracted voice profile if available
            voice_profile_section = ""
            try:
                from core.style.profile import get_or_refresh_style_profile

                profile = await get_or_refresh_style_profile(task.mailbox_id, session)
                if profile:
                    voice_profile_section = (
                        f"\n\n## EXTRACTED VOICE PROFILE\n"
                        f"Tone: {profile.tone}\n"
                        f"Formality: {profile.formality_level}/5\n"
                        f"Sentence length: {profile.avg_sentence_length}\n"
                        f"Greeting: {profile.greeting_style}\n"
                        f"Closing: {profile.closing_style}\n"
                        f"Vocabulary: {', '.join(profile.vocabulary_traits[:5])}\n"
                        f"Sample phrases: {', '.join(profile.sample_phrases[:5])}\n"
                    )
            except Exception as profile_exc:
                log.debug("draft.voice_profile_skipped", error=str(profile_exc))

            # Build system prompt with mandatory writing-style policy
            system_prompt = (
                get_system_prompt_preamble()
                + "\n\n## REQUIRED WRITING STYLE POLICY\n"
                + _WRITING_STYLE
                + voice_profile_section
                + "\n\n## TASK\n"
                + task_directive
                + "\nDo not invent facts. Do not include a sign-off (user will add their own).\n"
            )
            if style_instructions:
                system_prompt += "\n## USER STYLE INSTRUCTIONS\n" + "\n".join(f"- {s}" for s in style_instructions)

            # Build user message with thread context
            thread_context = ""
            if thread_messages:
                thread_parts = []
                for msg in thread_messages:
                    msg_body, _ = sanitize_for_llm(msg.snippet or msg.body_text or "", "email")
                    thread_parts.append(
                        f"  From: {msg.from_address}\n"
                        f"  Date: {msg.received_at}\n"
                        f"  {msg_body[:500]}\n"
                    )
                thread_context = (
                    "Thread history (oldest first):\n"
                    + "---\n".join(thread_parts)
                    + "\n---\n"
                )

            user_message = (
                f"{thread_context}"
                f"Email to reply to:\n"
                f"From: {email.from_address}\n"
                f"Subject: {sanitized_subject}\n"
                f"Body:\n{sanitized_body}\n"
            )

            llm = get_llm_client()
            response = await llm.complete(
                system=system_prompt,
                user=user_message,
                max_tokens=600,
                temperature=0.3,
                response_format="json",
                mailbox_id=str(task.mailbox_id),
            )

            import json
            parsed = json.loads(response.content)
            draft_text = parsed.get("body", "")
            subject_line = parsed.get("subject", f"Re: {email.subject or ''}")
            grounding_score = float(parsed.get("grounding_confidence", 0.8))

            # Deterministic style-conformance score (no LLM). Closes SLO 3.e.
            from core.style.conformance import score_style_value
            style_conformance_score = score_style_value(draft_text)

            # Hallucination check: flag if grounding score is low
            hallucination_flag = grounding_score < 0.6

            # Quality gate: reject drafts below grounding threshold
            if grounding_score < 0.4:
                log.warning(
                    "draft.rejected_low_grounding",
                    grounding_score=grounding_score,
                    email_id=str(task.email_id),
                    correlation_id=task.correlation_id,
                )
                draft = Draft(
                    id=uuid.uuid4(),
                    email_id=task.email_id,
                    mailbox_id=task.mailbox_id,
                    user_id=task.user_id,
                    draft_text=draft_text,
                    subject_line=subject_line,
                    prompt_version=prompt_version,
                    model_id=response.model_id,
                    policy_version=task.policy_version,
                    grounding_score=grounding_score,
                    hallucination_flag=True,
                    status=DraftStatus.REJECTED,
                    correlation_id=task.correlation_id,
                )
                session.add(draft)
                await session.flush()
                return DraftResult(
                    draft_id=draft.id,
                    gmail_draft_id=None,
                    draft_text=draft_text,
                    subject_line=subject_line,
                    grounding_score=grounding_score,
                    hallucination_flag=True,
                    style_conformance_score=style_conformance_score,
                )

            # Write to Gmail Drafts — this is a CREATE operation only, never send
            gmail_draft_id: str | None = None
            try:
                mailbox_backend = get_mailbox_backend(mailbox)
                gmail_draft = mailbox_backend.create_draft(
                    thread_id=email.gmail_thread_id,
                    to=email.from_address or "",
                    subject=subject_line,
                    body_text=draft_text,
                    in_reply_to=email.gmail_message_id,
                )
                gmail_draft_id = gmail_draft.get("id")
            except Exception as exc:
                log.warning(
                    "draft.gmail_write_failed",
                    error=str(exc),
                    email_id=str(task.email_id),
                    correlation_id=task.correlation_id,
                )

            # Persist draft record
            draft = Draft(
                id=uuid.uuid4(),
                email_id=task.email_id,
                mailbox_id=task.mailbox_id,
                user_id=task.user_id,
                gmail_draft_id=gmail_draft_id,
                draft_text=draft_text,
                subject_line=subject_line,
                prompt_version="v1",
                model_id=response.model_id,
                policy_version=task.policy_version,
                style_profile_version=task.style_profile_version,
                grounding_score=grounding_score,
                hallucination_flag=hallucination_flag,
                style_conformance_score=style_conformance_score,
                status=DraftStatus.GENERATED,
                correlation_id=task.correlation_id,
            )
            session.add(draft)
            await session.flush()

            log.info(
                "draft.generated",
                draft_id=str(draft.id),
                gmail_draft_id=gmail_draft_id,
                grounding_score=grounding_score,
                hallucination_flag=hallucination_flag,
                correlation_id=task.correlation_id,
            )

            return DraftResult(
                draft_id=draft.id,
                gmail_draft_id=gmail_draft_id,
                draft_text=draft_text,
                subject_line=subject_line,
                grounding_score=grounding_score,
                hallucination_flag=hallucination_flag,
                style_conformance_score=style_conformance_score,
            )
