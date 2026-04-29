"""
SafetyAgent — prompt-injection detection, policy violation checks, mutation safeguards.
Always runs BEFORE any LLM call or mailbox mutation.
Deterministic-first: no LLM needed for safety checks.
"""

from __future__ import annotations

import structlog

from core.config import settings
from core.schemas.contracts import (
    AgentResponse,
    MutationGuardResult,
    MutationGuardTask,
    SafetyCheckResult,
    SafetyCheckTask,
)
from core.security.injection import detect_injection_threats, sanitize_for_llm
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)


class SafetyAgent(BaseAgent[SafetyCheckTask, SafetyCheckResult]):
    name = "safety_agent"

    def _check_kill_switches(self, task: SafetyCheckTask) -> bool:
        # Safety agent itself is never bypassed — it's the kill-switch enforcer
        return False

    async def _execute(self, task: SafetyCheckTask) -> SafetyCheckResult:
        if task.check_type == "prompt_injection":
            return await self._check_injection(task)
        elif task.check_type == "mutation_guard":
            raise ValueError("Use MutationGuardAgent for mutation checks")
        else:
            return SafetyCheckResult(passed=True, threats_detected=[])

    async def _check_injection(self, task: SafetyCheckTask) -> SafetyCheckResult:
        threats = detect_injection_threats(task.content)
        sanitized, blocked = sanitize_for_llm(task.content)

        if blocked:
            log.warning(
                "safety.injection.hard_block",
                email_id=str(task.email_id),
                mailbox_id=str(task.mailbox_id),
                correlation_id=task.correlation_id,
            )
            return SafetyCheckResult(
                passed=False,
                threats_detected=threats,
                sanitized_content=sanitized,
                blocked=True,
                block_reason="Hard-block injection pattern detected",
            )

        return SafetyCheckResult(
            passed=len(threats) == 0,
            threats_detected=threats,
            sanitized_content=sanitized,
            blocked=False,
        )


class MutationGuardAgent(BaseAgent[MutationGuardTask, MutationGuardResult]):
    """
    Guards every autonomous mailbox mutation.
    Enforces confidence thresholds and kill switches.
    Writes a MutationLedger entry with undo token before allowing any mutation.
    """

    name = "mutation_guard_agent"

    def _check_kill_switches(self, task: MutationGuardTask) -> bool:
        if settings.kill_switch_mutations:
            return True
        return False

    async def _execute(self, task: MutationGuardTask) -> MutationGuardResult:
        import secrets
        import uuid
        from datetime import datetime, timedelta, timezone

        from core.config import settings as cfg

        # Confidence gate
        if task.confidence < cfg.triage_medium_confidence_threshold:
            log.info(
                "mutation.blocked.low_confidence",
                confidence=task.confidence,
                threshold=cfg.triage_medium_confidence_threshold,
                email_id=str(task.email_id),
                correlation_id=task.correlation_id,
            )
            return MutationGuardResult(
                allowed=False,
                block_reason=f"Confidence {task.confidence:.2f} below threshold {cfg.triage_medium_confidence_threshold}",
            )

        # Generate undo token and ledger entry (DB write handled by caller/orchestrator)
        undo_token = secrets.token_urlsafe(32)
        undo_expires_at = datetime.now(tz=timezone.utc) + timedelta(
            seconds=cfg.mutation_undo_window_seconds
        )
        ledger_id = uuid.uuid4()

        log.info(
            "mutation.approved",
            mutation_type=task.mutation_type,
            confidence=task.confidence,
            email_id=str(task.email_id),
            undo_token=undo_token[:8] + "...",  # log prefix only
            correlation_id=task.correlation_id,
        )

        return MutationGuardResult(
            allowed=True,
            ledger_id=ledger_id,
            undo_token=undo_token,
        )
