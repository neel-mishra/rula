"""
BriefAgent — per-mailbox scheduled digest composition.
No cross-mailbox unified brief mode (by design).
Applies writing-style.md to all generated content.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from core.config import settings
from core.schemas.contracts import BriefResult, BriefTask
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)

# Load writing style once — blocks pipeline if missing
def _load_writing_style() -> str:
    import os
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "skills", "writing-style.md"),
        "/Users/neelmishra/.cursor/Rula/skills/writing-style.md",
    ]
    for path in candidates:
        normalized = os.path.normpath(path)
        if os.path.exists(normalized):
            with open(normalized) as f:
                return f.read()
    raise FileNotFoundError("skills/writing-style.md required for brief generation")


_WRITING_STYLE = _load_writing_style()

_BRIEF_CATEGORIES = ["newsletter", "update", "transaction", "fyi", "custom"]


class BriefAgent(BaseAgent[BriefTask, BriefResult]):
    name = "brief_agent"

    def _check_kill_switches(self, task: BriefTask) -> bool:
        return settings.kill_switch_llm

    async def _execute(self, task: BriefTask) -> BriefResult:
        from sqlalchemy import select, and_
        from core.db import get_db_session
        from core.models.brief import Brief, BriefItem, BriefStatus
        from core.models.email import Email
        from core.models.triage import TriageDecision, TriageOutcome
        from core.llm.client import get_llm_client
        from core.prompts.experiments import resolve_variant
        from core.prompts.registry import get_prompt_registry
        from core.security.injection import get_system_prompt_preamble, sanitize_for_llm

        async with get_db_session() as session:
            brief = await session.get(Brief, task.brief_id)
            if not brief or brief.mailbox_id != task.mailbox_id:
                raise ValueError(f"Brief {task.brief_id} not found or mailbox mismatch")

            # Resolve A/B variant for this mailbox (if any active experiment)
            variant = await resolve_variant("brief_summarizer", task.mailbox_id, session)
            prompt_version = variant.prompt_version if variant else "v1"
            registered = get_prompt_registry().get("brief_summarizer", prompt_version)
            summarizer_directive = registered.template if registered else (
                "Summarize this email for a brief digest. "
                'Return JSON: {"category": "...", "summary": "...", "key_points": [...], "importance_score": 0.0-1.0}'
            )

            # Fetch emails queued for this brief window — mailbox_id scoped
            brief_emails_result = await session.execute(
                select(Email)
                .join(TriageDecision, TriageDecision.email_id == Email.id)
                .where(
                    Email.mailbox_id == task.mailbox_id,
                    Email.received_at >= task.time_window_start,
                    Email.received_at < task.time_window_end,
                    TriageDecision.outcome == TriageOutcome.BRIEF_ONLY,
                )
                .order_by(Email.received_at.desc())
                .limit(100)
            )
            emails = brief_emails_result.scalars().all()

            if not emails:
                brief.status = BriefStatus.SKIPPED
                brief.item_count = 0
                log.info("brief.skipped_no_items", brief_id=str(task.brief_id), window=task.window)
                return BriefResult(brief_id=task.brief_id, item_count=0)

            brief.status = BriefStatus.GENERATING

            # Generate summary for each email via LLM
            llm = get_llm_client()
            items: list[BriefItem] = []

            for i, email in enumerate(emails):
                sanitized_body, blocked = sanitize_for_llm(
                    email.snippet or email.body_text or "", "email"
                )
                if blocked:
                    continue

                system_prompt = (
                    get_system_prompt_preamble()
                    + "\n\n## REQUIRED WRITING STYLE POLICY\n"
                    + _WRITING_STYLE
                    + "\n\n## TASK\n"
                    + summarizer_directive
                    + "\nValid categories: newsletter | update | transaction | fyi\n"
                )

                attachment_context = ""
                attachment_extracts = email.attachment_extracts or []
                textual_attachments = [
                    a for a in attachment_extracts if a.get("extracted_text")
                ]
                if textual_attachments:
                    lines = ["Attachments:"]
                    for att in textual_attachments[:3]:
                        excerpt = (att.get("extracted_text") or "")[:800]
                        lines.append(
                            f"  - {att.get('filename')} ({att.get('mime_type')}): {excerpt}"
                        )
                    attachment_context = "\n".join(lines) + "\n"

                user_msg = (
                    f"From: {email.from_address}\n"
                    f"Subject: {email.subject}\n"
                    f"Content: {sanitized_body}\n"
                    f"{attachment_context}"
                )

                try:
                    from core.llm.client import ModelTier

                    response = await llm.complete(
                        system=system_prompt,
                        user=user_msg,
                        max_tokens=300,
                        temperature=0.2,
                        response_format="json",
                        mailbox_id=str(task.mailbox_id),
                        tier=ModelTier.LOW,
                    )
                    import json
                    parsed = json.loads(response.content)
                except Exception as exc:
                    log.warning("brief.item_summarization_failed", error=str(exc), email_id=str(email.id))
                    parsed = {
                        "category": "fyi",
                        "summary": email.snippet or "(no content)",
                        "key_points": [],
                        "importance_score": 0.3,
                    }

                category = parsed.get("category", "fyi")
                if category not in _BRIEF_CATEGORIES:
                    category = "fyi"

                gmail_url = f"https://mail.google.com/mail/u/0/#inbox/{email.gmail_thread_id}"

                key_points = list(parsed.get("key_points") or [])
                if textual_attachments:
                    names = ", ".join(
                        (a.get("filename") or "attachment")
                        for a in textual_attachments[:3]
                    )
                    key_points.append(f"Attachments: {names}")

                item = BriefItem(
                    id=uuid.uuid4(),
                    brief_id=task.brief_id,
                    email_id=email.id,
                    mailbox_id=task.mailbox_id,
                    category=category,
                    summary=parsed.get("summary", ""),
                    key_points=key_points,
                    gmail_open_url=gmail_url,
                    importance_score=float(parsed.get("importance_score", 0.5)),
                    sort_order=i,
                )
                session.add(item)
                items.append(item)

            # Sort items by importance (highest first) before composing
            items.sort(key=lambda item: item.importance_score or 0.0, reverse=True)
            for idx, item in enumerate(items):
                item.sort_order = idx

            # Compose full brief HTML
            brief_html = self._compose_brief_html(items, task.window)
            brief_text = self._compose_brief_text(items, task.window)

            brief.body_html = brief_html
            brief.body_text = brief_text
            brief.subject_line = f"{'Morning' if task.window == 'morning' else 'Afternoon'} Brief — {len(items)} items"
            brief.item_count = len(items)
            brief.prompt_version = prompt_version

            # Deliver via SES if enabled
            ses_message_id = None
            if settings.ses_enabled and not settings.shadow_mode:
                try:
                    from core.email.ses import get_ses_client
                    from core.models.mailbox import Mailbox

                    mailbox = await session.get(Mailbox, task.mailbox_id)
                    if mailbox and mailbox.gmail_email:
                        ses = get_ses_client()
                        ses_message_id = await ses.send_brief(mailbox.gmail_email, brief)
                        brief.delivery_email_id = ses_message_id
                        brief.status = BriefStatus.DELIVERED
                        brief.delivered_at = datetime.now(tz=timezone.utc)
                    else:
                        brief.status = BriefStatus.DELIVERY_FAILED
                except Exception as ses_exc:
                    log.error("brief.ses_delivery_failed", error=str(ses_exc), brief_id=str(task.brief_id))
                    brief.status = BriefStatus.DELIVERY_FAILED
            else:
                brief.status = BriefStatus.DELIVERED
                brief.delivered_at = datetime.now(tz=timezone.utc)

            await session.flush()

            log.info(
                "brief.generated",
                brief_id=str(task.brief_id),
                item_count=len(items),
                window=task.window,
                correlation_id=task.correlation_id,
            )

            return BriefResult(
                brief_id=task.brief_id,
                item_count=len(items),
                delivered_at=brief.delivered_at,
            )

    def _compose_brief_html(self, items: list, window: str) -> str:
        label = "Morning" if window == "morning" else "Afternoon"
        lines = [f"<h2>{label} Brief ({len(items)} items)</h2>"]
        by_cat: dict[str, list] = {}
        for item in items:
            by_cat.setdefault(item.category, []).append(item)
        for cat, cat_items in by_cat.items():
            lines.append(f"<h3>{cat.title()}</h3><ul>")
            for item in cat_items:
                lines.append(
                    f'<li><a href="{item.gmail_open_url}">{item.summary}</a></li>'
                )
            lines.append("</ul>")
        return "\n".join(lines)

    def _compose_brief_text(self, items: list, window: str) -> str:
        label = "Morning" if window == "morning" else "Afternoon"
        lines = [f"{label} Brief — {len(items)} items\n"]
        by_cat: dict[str, list] = {}
        for item in items:
            by_cat.setdefault(item.category, []).append(item)
        for cat, cat_items in by_cat.items():
            lines.append(f"\n{cat.upper()}")
            for item in cat_items:
                lines.append(f"  • {item.summary}")
                lines.append(f"    {item.gmail_open_url}")
        return "\n".join(lines)
