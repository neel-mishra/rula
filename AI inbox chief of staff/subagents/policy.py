"""
PolicyAgent — compiles user instructions into executable policy rules.
Converts natural-language preferences into durable Memory entries with structured_data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from core.schemas.contracts import PolicyCompileResult, PolicyCompileTask
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)


class PolicyAgent(BaseAgent[PolicyCompileTask, PolicyCompileResult]):
    name = "policy_agent"

    async def _execute(self, task: PolicyCompileTask) -> PolicyCompileResult:
        from core.db import get_db_session
        from core.llm.client import get_llm_client
        from core.models.memory import Memory, MemoryScope, MemoryType
        from core.security.injection import get_system_prompt_preamble

        llm = get_llm_client()

        # Step 1: Check if instruction is ambiguous and needs clarification
        analysis = await self._analyze_instruction(llm, task.instruction_text)

        if analysis.get("needs_clarification"):
            log.info(
                "policy.needs_clarification",
                question=analysis["clarification_question"],
                correlation_id=task.correlation_id,
            )
            return PolicyCompileResult(
                rules_created=0,
                rules_updated=0,
                policy_version=task.policy_version,
                needs_clarification=True,
                clarification_question=analysis["clarification_question"],
            )

        # Step 2: Extract rules from clear instruction
        rules = await self._extract_rules(llm, task.instruction_text)

        created = 0
        async with get_db_session() as session:
            for rule in rules:
                scope_str = rule.get("scope", "mailbox_specific")
                scope = MemoryScope.USER_GLOBAL if scope_str == "user_global" else MemoryScope.MAILBOX_SPECIFIC
                mailbox_id = task.mailbox_id if scope == MemoryScope.MAILBOX_SPECIFIC else None

                memory = Memory(
                    id=uuid.uuid4(),
                    user_id=task.user_id,
                    mailbox_id=mailbox_id,
                    scope=scope,
                    applies_to_all_mailboxes=rule.get("applies_to_all_mailboxes", False),
                    memory_type=MemoryType.POLICY,
                    content=rule.get("content", task.instruction_text),
                    structured_data={
                        "rule": rule.get("rule_type", ""),
                        "targets": rule.get("targets", []),
                        "source_instruction": task.instruction_text,
                    },
                    source=task.source,
                    confidence=float(rule.get("confidence", 0.85)),
                    is_active=True,
                    last_reinforced_at=datetime.now(tz=timezone.utc),
                )
                session.add(memory)
                created += 1

            await session.flush()

        log.info(
            "policy.compiled",
            rules_created=created,
            source=task.source,
            correlation_id=task.correlation_id,
        )

        return PolicyCompileResult(
            rules_created=created,
            rules_updated=0,
            policy_version=task.policy_version,
        )

    async def _analyze_instruction(self, llm, instruction_text: str) -> dict:
        import json
        from core.security.injection import get_system_prompt_preamble

        system_prompt = (
            get_system_prompt_preamble()
            + "\n\nAnalyze whether this user instruction is clear enough to create email rules. "
            + "Return JSON: {\n"
            + '  "needs_clarification": true/false,\n'
            + '  "clarification_question": "question to ask if ambiguous, else null",\n'
            + '  "ambiguity_reason": "why it is ambiguous, else null"\n'
            + "}\n"
            + "Flag as needing clarification if:\n"
            + "- No specific sender/domain/category is mentioned and the instruction is about routing\n"
            + "- The instruction contradicts common sense (e.g., 'archive everything')\n"
            + "- The scope is unclear (one mailbox vs all?)\n"
            + "- The action is unclear (inbox vs brief vs draft?)\n"
            + "If the instruction is clear and actionable, set needs_clarification=false."
        )

        response = await llm.complete(
            system=system_prompt,
            user=f"Instruction: {instruction_text}",
            max_tokens=200,
            temperature=0.1,
            response_format="json",
        )
        return json.loads(response.content)

    async def _extract_rules(self, llm, instruction_text: str) -> list[dict]:
        import json
        from core.security.injection import get_system_prompt_preamble

        system_prompt = (
            get_system_prompt_preamble()
            + "\n\nParse the user instruction and extract ALL policy rules. "
            + "Return JSON array: [\n"
            + "  {\n"
            + '    "rule_type": "always_inbox|always_brief|never_archive|draft_always|never_draft",\n'
            + '    "targets": ["email@example.com", "domain.com", "newsletter"],\n'
            + '    "content": "human-readable rule description",\n'
            + '    "scope": "mailbox_specific|user_global",\n'
            + '    "applies_to_all_mailboxes": false,\n'
            + '    "confidence": 0.9\n'
            + "  }\n"
            + "]\n"
            + "scope=user_global only if user explicitly says 'all mailboxes'."
        )

        response = await llm.complete(
            system=system_prompt,
            user=f"Instruction: {instruction_text}",
            max_tokens=500,
            temperature=0.1,
            response_format="json",
        )
        rules = json.loads(response.content)
        if not isinstance(rules, list):
            rules = [rules]
        return rules
