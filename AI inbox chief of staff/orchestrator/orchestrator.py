"""
Orchestrator — owns end-to-end workflow state machine for each (mailbox_id, message_id).
Dispatches tasks to subagents with strict contracts, timeouts, and correlation IDs.
Enforces policy precedence: safety > mailbox rules > global preferences > model suggestion.
Handles retries, fallback paths, DLQ routing, and observability.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from core.config import settings
from core.schemas.contracts import (
    IngestionTask,
    MutationGuardTask,
    SafetyCheckTask,
    TriageTask,
    DraftTask,
)
from subagents.ingestion import IngestionAgent
from subagents.safety import SafetyAgent, MutationGuardAgent
from subagents.triage import TriageAgent
from subagents.draft import DraftAgent
from subagents.telemetry import emit_telemetry

log = structlog.get_logger(__name__)

# Stage timeouts (seconds)
_TIMEOUTS = {
    "ingestion": 30,
    "safety": 5,
    "triage": 60,
    "mutation_guard": 5,
    "draft": 60,
}

# Max retries per stage before DLQ routing
_MAX_RETRIES = 3


class Orchestrator:
    """
    Central execution coordinator.
    Stateless: all state lives in DB + queue messages.
    """

    def __init__(self) -> None:
        self._ingestion = IngestionAgent()
        self._safety = SafetyAgent()
        self._mutation_guard = MutationGuardAgent()
        self._triage = TriageAgent()
        self._draft = DraftAgent()

    async def process_new_email(
        self,
        user_id: uuid.UUID,
        mailbox_id: uuid.UUID,
        gmail_message_id: str,
        gmail_history_id: str,
        correlation_id: str | None = None,
        policy_version: str = "v1",
    ) -> dict[str, Any]:
        """
        Full pipeline: ingest -> safety check -> triage -> (mutation_guard -> label) -> (draft)
        Returns summary of all stage outcomes.
        """
        correlation_id = correlation_id or str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        bound_log = log.bind(
            correlation_id=correlation_id,
            mailbox_id=str(mailbox_id),
            gmail_message_id=gmail_message_id,
        )
        bound_log.info("orchestrator.pipeline.started")

        ctx_base = dict(
            user_id=user_id,
            mailbox_id=mailbox_id,
            correlation_id=correlation_id,
            policy_version=policy_version,
            run_id=run_id,
        )

        results: dict[str, Any] = {}

        # ── Stage 1: Ingestion ─────────────────────────────────────────────
        ingest_response = await asyncio.wait_for(
            self._ingestion.run(
                IngestionTask(
                    **ctx_base,
                    gmail_message_id=gmail_message_id,
                    gmail_history_id=gmail_history_id,
                )
            ),
            timeout=_TIMEOUTS["ingestion"],
        )

        await emit_telemetry(
            stage="ingestion_agent",
            event_type="stage.completed" if ingest_response.ok else "stage.failed",
            task_context=IngestionTask(**ctx_base, gmail_message_id=gmail_message_id, gmail_history_id=gmail_history_id),
            duration_ms=ingest_response.meta.duration_ms,
        )

        if not ingest_response.ok:
            bound_log.error("pipeline.failed.ingestion", error=ingest_response.error)
            return {"ok": False, "stage": "ingestion", "error": ingest_response.error}

        email_id = ingest_response.payload.email_id
        results["ingestion"] = {"email_id": str(email_id), "is_duplicate": ingest_response.payload.is_duplicate}

        if ingest_response.payload.is_duplicate:
            bound_log.info("pipeline.stopped.duplicate")
            return {"ok": True, "stopped_at": "ingestion", "reason": "duplicate", **results}

        # ── Stage 2: Safety check ──────────────────────────────────────────
        # Load email content for safety check
        from core.db import get_db_session
        from core.models.email import Email

        async with get_db_session() as session:
            email = await session.get(Email, email_id)
            content_to_check = (email.subject or "") + " " + (email.snippet or "")

        safety_response = await asyncio.wait_for(
            self._safety.run(
                SafetyCheckTask(
                    **ctx_base,
                    email_id=email_id,
                    content=content_to_check,
                    check_type="prompt_injection",
                )
            ),
            timeout=_TIMEOUTS["safety"],
        )

        if not safety_response.ok or (safety_response.payload and safety_response.payload.blocked):
            bound_log.warning(
                "pipeline.safety.blocked",
                threats=safety_response.payload.threats_detected if safety_response.payload else [],
            )
            results["safety"] = {"blocked": True}
            return {"ok": False, "stage": "safety", "blocked": True, **results}

        results["safety"] = {"passed": True, "threats": safety_response.payload.threats_detected if safety_response.payload else []}

        # ── Stage 3: Triage ────────────────────────────────────────────────
        triage_response = await asyncio.wait_for(
            self._triage.run(
                TriageTask(
                    **ctx_base,
                    email_id=email_id,
                    gmail_message_id=gmail_message_id,
                )
            ),
            timeout=_TIMEOUTS["triage"],
        )

        await emit_telemetry(
            stage="triage_agent",
            event_type="stage.completed" if triage_response.ok else "stage.failed",
            task_context=TriageTask(**ctx_base, email_id=email_id, gmail_message_id=gmail_message_id),
            duration_ms=triage_response.meta.duration_ms,
            extra={"outcome": triage_response.payload.outcome if triage_response.payload else "error"},
        )

        if not triage_response.ok:
            bound_log.error("pipeline.failed.triage", error=triage_response.error)
            return {"ok": False, "stage": "triage", "error": triage_response.error, **results}

        triage = triage_response.payload
        results["triage"] = {
            "outcome": triage.outcome,
            "confidence": triage.confidence,
            "method": triage.method,
        }

        # Persist triage decision to DB
        await self._persist_triage_decision(email_id, mailbox_id, user_id, triage, correlation_id, policy_version)

        # ── Stage 4: Mutation guard (if triage requires a mailbox action) ──
        # Respect per-mailbox activation mode: shadow=no mutations, observe=label only, auto=full
        mailbox_mode = await self._get_activation_mode(mailbox_id)
        is_shadow = settings.shadow_mode or mailbox_mode == "shadow"

        if triage.requires_mutation and not settings.kill_switch_mutations and not is_shadow:
            guard_response = await asyncio.wait_for(
                self._mutation_guard.run(
                    MutationGuardTask(
                        **ctx_base,
                        email_id=email_id,
                        mutation_type=triage.mutation_type or "label_add",
                        proposed_label_id=triage.label_id,
                        confidence=triage.confidence,
                        reason_trace=triage.reason_trace or "",
                    )
                ),
                timeout=_TIMEOUTS["mutation_guard"],
            )

            if guard_response.ok and guard_response.payload and guard_response.payload.allowed:
                await self._apply_mutation(
                    mailbox_id=mailbox_id,
                    email_id=email_id,
                    user_id=user_id,
                    triage=triage,
                    guard=guard_response.payload,
                    correlation_id=correlation_id,
                    policy_version=policy_version,
                )
                results["mutation"] = {
                    "applied": True,
                    "undo_token": guard_response.payload.undo_token,
                }
            else:
                results["mutation"] = {
                    "applied": False,
                    "block_reason": guard_response.payload.block_reason if guard_response.payload else "guard_failed",
                }

        # ── Stage 5: Draft (if draft_candidate) ───────────────────────────
        if triage.outcome == "draft_candidate":
            if is_shadow:
                bound_log.info("shadow_mode.draft_skipped", email_id=str(email_id))
                results["draft"] = {"ok": True, "shadow_mode": True, "gmail_draft_id": None}
            else:
                async with get_db_session() as session:
                    email_obj = await session.get(Email, email_id)
                    thread_id = email_obj.gmail_thread_id if email_obj else ""

                draft_response = await asyncio.wait_for(
                    self._draft.run(
                        DraftTask(
                            **ctx_base,
                            email_id=email_id,
                            gmail_thread_id=thread_id,
                        )
                    ),
                    timeout=_TIMEOUTS["draft"],
                )

                results["draft"] = {
                    "ok": draft_response.ok,
                    "draft_id": str(draft_response.payload.draft_id) if draft_response.payload else None,
                    "gmail_draft_id": draft_response.payload.gmail_draft_id if draft_response.payload else None,
                }

        # ── Emit audit event ───────────────────────────────────────────────
        await self._emit_audit_event(
            user_id=user_id,
            mailbox_id=mailbox_id,
            email_id=email_id,
            results=results,
            correlation_id=correlation_id,
        )

        if is_shadow:
            results["shadow_mode"] = True
            results["activation_mode"] = mailbox_mode

        bound_log.info("orchestrator.pipeline.completed", outcome=results.get("triage", {}).get("outcome"), shadow=settings.shadow_mode)
        return {"ok": True, "email_id": str(email_id), **results}

    async def _get_activation_mode(self, mailbox_id) -> str:
        """Get per-mailbox activation mode. Falls back to global default."""
        from core.db import get_db_session
        from core.models.mailbox import Mailbox

        async with get_db_session() as session:
            mailbox = await session.get(Mailbox, mailbox_id)
            if mailbox and hasattr(mailbox, "activation_mode"):
                return mailbox.activation_mode
        return settings.default_activation_mode

    async def _persist_triage_decision(
        self, email_id, mailbox_id, user_id, triage, correlation_id, policy_version
    ) -> None:
        import uuid
        from core.db import get_db_session
        from core.models.triage import TriageDecision, TriageMethod, TriageOutcome

        async with get_db_session() as session:
            decision = TriageDecision(
                id=uuid.uuid4(),
                email_id=email_id,
                mailbox_id=mailbox_id,
                user_id=user_id,
                outcome=TriageOutcome(triage.outcome),
                confidence=triage.confidence,
                method=TriageMethod(triage.method),
                rule_matched=triage.rule_matched,
                model_id=triage.model_id,
                policy_version=policy_version,
                prompt_version=getattr(triage, "prompt_version", None),
                reason_trace=triage.reason_trace,
                correlation_id=correlation_id,
            )
            session.add(decision)
            await session.flush()

    async def _apply_mutation(
        self, mailbox_id, email_id, user_id, triage, guard, correlation_id, policy_version
    ) -> None:
        from datetime import timedelta
        import uuid
        from core.db import get_db_session
        from core.models.mailbox import Mailbox
        from core.models.email import Email
        from core.models.mutation_ledger import MutationLedger, MutationStatus, MutationType
        from core.gmail import GmailClient

        async with get_db_session() as session:
            mailbox = await session.get(Mailbox, mailbox_id)
            email_obj = await session.get(Email, email_id)
            if not mailbox or not email_obj:
                return

            # Write ledger entry before mutation
            ledger = MutationLedger(
                id=guard.ledger_id,
                email_id=email_id,
                mailbox_id=mailbox_id,
                user_id=user_id,
                mutation_type=MutationType.LABEL_ADD,
                status=MutationStatus.PENDING,
                prior_state={"labels": email_obj.gmail_labels},
                new_state={"labels": email_obj.gmail_labels + [mailbox.label_next_brief or ""]},
                label_id=mailbox.label_next_brief,
                reason_trace=triage.reason_trace or "",
                policy_version=policy_version,
                undo_token=guard.undo_token,
                undo_expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=settings.mutation_undo_window_seconds),
                correlation_id=correlation_id,
            )
            session.add(ledger)
            await session.flush()

            # Apply Gmail mutation
            try:
                if mailbox.label_next_brief:
                    gmail = GmailClient(mailbox)
                    gmail.modify_message_labels(
                        message_id=email_obj.gmail_message_id,
                        add_label_ids=[mailbox.label_next_brief],
                    )
                ledger.status = MutationStatus.APPLIED
                ledger.applied_at = datetime.now(tz=timezone.utc)
            except Exception as exc:
                log.error("mutation.gmail_apply_failed", error=str(exc), correlation_id=correlation_id)
                ledger.status = MutationStatus.UNDO_FAILED

    async def _emit_audit_event(
        self, user_id, mailbox_id, email_id, results, correlation_id
    ) -> None:
        import uuid
        from core.db import get_db_session
        from core.models.audit import AuditEvent

        async with get_db_session() as session:
            event = AuditEvent(
                id=uuid.uuid4(),
                user_id=user_id,
                mailbox_id=mailbox_id,
                event_type="triage.decision",
                actor="system",
                resource_type="email",
                resource_id=str(email_id),
                payload=results,
                severity="info",
                correlation_id=correlation_id,
            )
            session.add(event)
            await session.flush()
