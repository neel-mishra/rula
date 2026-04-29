"""
TriageAgent — hybrid triage: deterministic rules → LLM classifier → retrieval context.
Policy precedence: safety > mailbox rules > global preferences > model suggestion.
Falls back to deterministic if LLM unavailable (kill switch or provider error).
"""

from __future__ import annotations

import structlog

from core.config import settings
from core.models.triage import TriageMethod, TriageOutcome
from core.schemas.contracts import TriageResult, TriageTask
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic rule engine
# ─────────────────────────────────────────────────────────────────────────────

class TriageRule:
    """Immutable rule: returns (outcome, confidence, rule_name) or None."""
    name: str

    def evaluate(self, email_features: dict, memories: list[dict]) -> tuple[TriageOutcome, float, str] | None:
        raise NotImplementedError


class AlwaysInboxRule(TriageRule):
    """Highest precedence: sender/thread explicitly protected."""
    name = "always_inbox"

    def evaluate(self, email_features: dict, memories: list[dict]) -> tuple[TriageOutcome, float, str] | None:
        sender = email_features.get("from_address", "").lower()
        domain = email_features.get("from_domain", "").lower()
        for mem in memories:
            structured = mem.get("structured_data", {})
            if structured.get("rule") == "always_inbox":
                targets = [t.lower() for t in structured.get("targets", [])]
                if sender in targets or domain in targets:
                    return TriageOutcome.PROTECTED, 1.0, self.name
        return None


class NewsletterRule(TriageRule):
    """Newsletters with list-unsubscribe header go to brief unless VIP."""
    name = "newsletter_brief"

    def evaluate(self, email_features: dict, memories: list[dict]) -> tuple[TriageOutcome, float, str] | None:
        if email_features.get("is_newsletter") and not email_features.get("sender_vip"):
            return TriageOutcome.BRIEF_ONLY, 0.95, self.name
        return None


class DirectReplyRule(TriageRule):
    """Direct replies to user stay in inbox."""
    name = "direct_reply_inbox"

    def evaluate(self, email_features: dict, memories: list[dict]) -> tuple[TriageOutcome, float, str] | None:
        if email_features.get("is_reply") and email_features.get("is_direct_to_user"):
            return TriageOutcome.INBOX_KEEP, 0.92, self.name
        return None


_DEFAULT_RULES: list[TriageRule] = [
    AlwaysInboxRule(),
    NewsletterRule(),
    DirectReplyRule(),
]


def run_rule_engine(
    email_features: dict, memories: list[dict]
) -> tuple[TriageOutcome, float, str] | None:
    """Run rules in priority order. First match wins."""
    for rule in _DEFAULT_RULES:
        result = rule.evaluate(email_features, memories)
        if result is not None:
            return result
    return None


# ─────────────────────────────────────────────────────────────────────────────
# TriageAgent
# ─────────────────────────────────────────────────────────────────────────────

class TriageAgent(BaseAgent[TriageTask, TriageResult]):
    name = "triage_agent"

    def _check_kill_switches(self, task: TriageTask) -> bool:
        # Triage always runs; LLM path controlled internally
        return False

    async def _execute(self, task: TriageTask) -> TriageResult:
        from sqlalchemy import select
        from core.db import get_db_session
        from core.models.email import Email
        from core.models.memory import Memory, MemoryScope
        from core.models.triage import TriageDecision

        async with get_db_session() as session:
            # Load email — mailbox isolation enforced via mailbox_id filter
            email = await session.get(Email, task.email_id)
            if not email or email.mailbox_id != task.mailbox_id:
                raise ValueError(f"Email {task.email_id} not found or mailbox mismatch")

            # Load mailbox-scoped memories + high-confidence user-global memories
            mem_result = await session.execute(
                select(Memory).where(
                    (
                        (Memory.mailbox_id == task.mailbox_id)
                        | (
                            (Memory.scope == MemoryScope.USER_GLOBAL)
                            & (Memory.applies_to_all_mailboxes == True)  # noqa: E712
                            & (Memory.confidence >= 0.8)
                        )
                    ),
                    Memory.user_id == task.user_id,
                    Memory.is_active == True,  # noqa: E712
                )
            )
            memories = [
                {"memory_type": m.memory_type, "content": m.content, "structured_data": m.structured_data}
                for m in mem_result.scalars().all()
            ]

            email_features = dict(email.features)
            email_features["from_address"] = email.from_address or ""
            email_features["from_domain"] = email.from_domain or ""
            email_features["subject"] = email.subject or ""
            email_features["is_reply"] = email_features.get("is_reply", False)

            # 1) Deterministic rules (always runs first)
            rule_result = run_rule_engine(email_features, memories)

            if rule_result is not None:
                outcome, confidence, rule_name = rule_result
                log.info(
                    "triage.rule_match",
                    rule=rule_name,
                    outcome=outcome,
                    confidence=confidence,
                    email_id=str(task.email_id),
                    correlation_id=task.correlation_id,
                )
                return self._build_result(
                    task, email, outcome, confidence,
                    method=TriageMethod.DETERMINISTIC,
                    rule_matched=rule_name,
                )

            # 2) Retrieve similar past emails for RAG context
            similar_context = await self._retrieve_similar_emails(task, email, session)

            # 3) LLM classification (if kill switch not active)
            if not settings.kill_switch_llm:
                try:
                    # Resolve A/B variant for this mailbox (if any active experiment)
                    from core.prompts.experiments import resolve_variant
                    variant = await resolve_variant(
                        "triage_classifier", task.mailbox_id, session
                    )
                    prompt_version = variant.prompt_version if variant else "v1"
                    return await self._llm_classify(
                        task, email, email_features, memories, similar_context,
                        prompt_version=prompt_version,
                    )
                except Exception as exc:
                    log.warning(
                        "triage.llm_failed_fallback",
                        error=str(exc),
                        correlation_id=task.correlation_id,
                    )
                    # Fall through to deterministic fallback

            # 4) Deterministic fallback: conservative — keep in inbox
            log.info(
                "triage.deterministic_fallback",
                email_id=str(task.email_id),
                correlation_id=task.correlation_id,
            )
            return self._build_result(
                task, email,
                outcome=TriageOutcome.INBOX_KEEP,
                confidence=0.50,
                method=TriageMethod.FALLBACK,
                reason_trace="LLM unavailable; conservative fallback: keep in inbox",
            )

    async def _retrieve_similar_emails(self, task: TriageTask, email, session) -> list[dict]:
        """Retrieve similar past emails via pgvector for RAG context."""
        from core.models.email import Email
        from core.models.triage import TriageDecision

        if not (hasattr(Email, "embedding") and Email.embedding is not None):
            return []
        if email.embedding is None:
            return []

        try:
            from sqlalchemy import select

            result = await session.execute(
                select(Email, TriageDecision)
                .join(TriageDecision, TriageDecision.email_id == Email.id)
                .where(
                    Email.mailbox_id == task.mailbox_id,
                    Email.id != email.id,
                    Email.embedding.isnot(None),
                )
                .order_by(Email.embedding.cosine_distance(email.embedding))
                .limit(5)
            )
            rows = result.all()
            return [
                {
                    "from": e.from_address,
                    "subject": e.subject,
                    "outcome": td.outcome.value,
                    "confidence": td.confidence,
                }
                for e, td in rows
            ]
        except Exception as exc:
            log.debug("triage.rag_retrieval_failed", error=str(exc))
            return []

    async def _llm_classify(
        self, task: TriageTask, email, email_features: dict, memories: list[dict],
        similar_context: list[dict] | None = None,
        prompt_version: str = "v1",
    ) -> TriageResult:
        """LLM-based classification with prompt-injection defense."""
        from core.security.injection import get_system_prompt_preamble, sanitize_for_llm
        from core.llm.client import get_llm_client
        from core.prompts.registry import get_prompt_registry

        client = get_llm_client()
        registered = get_prompt_registry().get("triage_classifier", prompt_version)
        template_body = registered.template if registered else (
            "Classify the following email. Return JSON: "
            '{"outcome": "inbox_keep"|"brief_only"|"draft_candidate", '
            '"confidence": 0.0-1.0, "reason": "..."}'
        )

        # Sanitize untrusted email content
        sanitized_subject, blocked_s = sanitize_for_llm(email.subject or "", "subject")
        sanitized_body, blocked_b = sanitize_for_llm(email.snippet or "", "email")

        if blocked_s or blocked_b:
            log.warning(
                "triage.injection_block",
                email_id=str(task.email_id),
                correlation_id=task.correlation_id,
            )
            return self._build_result(
                task, email,
                outcome=TriageOutcome.INBOX_KEEP,
                confidence=0.5,
                method=TriageMethod.FALLBACK,
                reason_trace="Injection detected in email content; fallback to inbox-keep",
            )

        system_prompt = (
            get_system_prompt_preamble()
            + template_body
            + "\nOutcomes:\n"
            "- inbox_keep: urgent, actionable, direct ask from human\n"
            "- brief_only: newsletters, updates, FYI, low urgency\n"
            "- draft_candidate: inbox_keep AND a reply is warranted\n"
        )

        memory_context = "\n".join(
            f"- {m['content']}" for m in memories[:10]
        )

        rag_context = ""
        if similar_context:
            rag_lines = []
            for sc in similar_context:
                rag_lines.append(
                    f"  - From: {sc['from']}, Subject: {sc['subject']} → {sc['outcome']} ({sc['confidence']:.0%})"
                )
            rag_context = "\nSimilar past emails and how they were triaged:\n" + "\n".join(rag_lines) + "\n"

        user_message = (
            f"User preferences:\n{memory_context}\n"
            f"{rag_context}\n"
            f"From: {email_features.get('from_address', '')}\n"
            f"Subject: {sanitized_subject}\n"
            f"Snippet: {sanitized_body}\n"
            f"Is newsletter: {email_features.get('is_newsletter', False)}\n"
            f"Is reply: {email_features.get('is_reply', False)}\n"
        )

        response = await client.complete(
            system=system_prompt,
            user=user_message,
            max_tokens=200,
            response_format="json",
            mailbox_id=str(task.mailbox_id),
        )

        import json
        parsed = json.loads(response.content)
        outcome_str = parsed.get("outcome", "inbox_keep")
        confidence = float(parsed.get("confidence", 0.7))
        reason = parsed.get("reason", "")

        try:
            outcome = TriageOutcome(outcome_str)
        except ValueError:
            outcome = TriageOutcome.INBOX_KEEP
            confidence = 0.5

        return self._build_result(
            task, email, outcome, confidence,
            method=TriageMethod.LLM,
            model_id=client.model_id,
            reason_trace=reason,
            prompt_version=prompt_version,
        )

    def _build_result(
        self,
        task: TriageTask,
        email,
        outcome: TriageOutcome,
        confidence: float,
        method: TriageMethod,
        rule_matched: str | None = None,
        model_id: str | None = None,
        reason_trace: str | None = None,
        prompt_version: str | None = None,
    ) -> TriageResult:
        requires_mutation = outcome in (TriageOutcome.BRIEF_ONLY,) and confidence >= settings.triage_medium_confidence_threshold
        return TriageResult(
            email_id=task.email_id,
            outcome=outcome.value,
            confidence=confidence,
            method=method.value,
            rule_matched=rule_matched,
            model_id=model_id,
            reason_trace=reason_trace,
            requires_mutation=requires_mutation,
            mutation_type="label_add" if requires_mutation else None,
            prompt_version=prompt_version,
        )
