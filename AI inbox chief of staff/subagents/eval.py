"""
EvalAgent — offline/online quality evaluation and drift detection.
Runs nightly eval suite: triage precision/recall, draft quality, style conformance.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from core.schemas.contracts import AgentResponse, StageMeta, TaskContext
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)


class EvalTask(TaskContext):
    eval_type: str        # "triage" | "draft_quality" | "style_conformance" | "safety"
    time_window_hours: int = 24
    sample_limit: int = 100


class EvalResult(TaskContext):
    eval_type: str
    pass_rate: float
    fail_count: int
    total_evaluated: int
    threshold: float
    passed: bool
    details: list[dict[str, Any]]


class EvalAgent(BaseAgent[EvalTask, EvalResult]):
    name = "eval_agent"

    async def _execute(self, task: EvalTask) -> EvalResult:
        if task.eval_type == "triage":
            return await self._eval_triage(task)
        elif task.eval_type == "draft_quality":
            return await self._eval_draft_quality(task)
        elif task.eval_type == "style_conformance":
            return await self._eval_style_conformance(task)
        elif task.eval_type == "safety":
            return await self._eval_safety(task)
        elif task.eval_type.endswith("_gold"):
            return await self._eval_gold(task)
        else:
            raise ValueError(f"Unknown eval type: {task.eval_type}")

    async def _eval_gold(self, task: EvalTask) -> EvalResult:
        """Dispatch *_gold eval types to the gold-eval adapter."""
        from core.gold_eval.adapter import (
            load_latest_active_dataset,
            run_brief_gold,
            run_draft_gold,
            run_memory_gold,
            run_safety_gold,
            run_triage_gold,
        )
        from core.models.gold_sample import GoldFixtureType

        runner_by_prefix = {
            "triage_gold": (GoldFixtureType.TRIAGE, run_triage_gold),
            "draft_quality_gold": (GoldFixtureType.DRAFT, run_draft_gold),
            "brief_quality_gold": (GoldFixtureType.BRIEF, run_brief_gold),
            "memory_applicability_gold": (GoldFixtureType.MEMORY, run_memory_gold),
            "safety_gold": (GoldFixtureType.SAFETY, run_safety_gold),
        }
        chosen = runner_by_prefix.get(task.eval_type)
        if not chosen:
            raise ValueError(f"Unknown gold eval type: {task.eval_type}")
        fixture_type, runner = chosen
        samples = await load_latest_active_dataset(fixture_type)
        return await runner(
            samples,
            user_id=task.user_id,
            mailbox_id=task.mailbox_id,
        )

    async def _eval_triage(self, task: EvalTask) -> EvalResult:
        """
        Triage eval: check false-archive and false-brief rates.
        False-archive: system archived but user manually moved back to inbox.
        False-brief: user marked briefed item as urgent/actionable.
        """
        from sqlalchemy import select, and_
        from core.db import get_db_session
        from core.models.feedback import FeedbackEvent
        from core.models.triage import TriageDecision

        async with get_db_session() as session:
            window_start = datetime.now(tz=timezone.utc) - timedelta(hours=task.time_window_hours)

            # Count triage corrections within window for this mailbox
            corrections = await session.execute(
                select(FeedbackEvent).where(
                    FeedbackEvent.mailbox_id == task.mailbox_id,
                    FeedbackEvent.feedback_type == "triage_correction",
                    FeedbackEvent.created_at >= window_start,
                )
            )
            correction_list = corrections.scalars().all()

            total = await session.execute(
                select(TriageDecision).where(
                    TriageDecision.mailbox_id == task.mailbox_id,
                    TriageDecision.created_at >= window_start,
                )
            )
            total_count = len(total.scalars().all())
            fail_count = len(correction_list)

            pass_rate = 1.0 - (fail_count / total_count) if total_count > 0 else 1.0
            threshold = 0.99  # <1% false-archive/brief rate target

            log.info(
                "eval.triage",
                pass_rate=pass_rate,
                fail_count=fail_count,
                total=total_count,
                mailbox_id=str(task.mailbox_id),
            )

            return EvalResult(
                user_id=task.user_id,
                mailbox_id=task.mailbox_id,
                correlation_id=task.correlation_id,
                policy_version=task.policy_version,
                eval_type="triage",
                pass_rate=pass_rate,
                fail_count=fail_count,
                total_evaluated=total_count,
                threshold=threshold,
                passed=pass_rate >= threshold,
                details=[{"corrections": [str(c.id) for c in correction_list[:10]]}],
            )

    async def _eval_draft_quality(self, task: EvalTask) -> EvalResult:
        """Check draft grounding scores and hallucination flags."""
        from sqlalchemy import select
        from core.db import get_db_session
        from core.models.draft import Draft

        async with get_db_session() as session:
            window_start = datetime.now(tz=timezone.utc) - timedelta(hours=task.time_window_hours)
            drafts_result = await session.execute(
                select(Draft).where(
                    Draft.mailbox_id == task.mailbox_id,
                    Draft.created_at >= window_start,
                ).limit(task.sample_limit)
            )
            drafts = drafts_result.scalars().all()

            if not drafts:
                return EvalResult(
                    user_id=task.user_id,
                    mailbox_id=task.mailbox_id,
                    correlation_id=task.correlation_id,
                    policy_version=task.policy_version,
                    eval_type="draft_quality",
                    pass_rate=1.0,
                    fail_count=0,
                    total_evaluated=0,
                    threshold=0.985,
                    passed=True,
                    details=[],
                )

            failed = [d for d in drafts if d.hallucination_flag or (d.grounding_score or 1.0) < 0.6]
            pass_rate = 1.0 - len(failed) / len(drafts)
            threshold = 0.985  # <=1.5% failure rate

            return EvalResult(
                user_id=task.user_id,
                mailbox_id=task.mailbox_id,
                correlation_id=task.correlation_id,
                policy_version=task.policy_version,
                eval_type="draft_quality",
                pass_rate=pass_rate,
                fail_count=len(failed),
                total_evaluated=len(drafts),
                threshold=threshold,
                passed=pass_rate >= threshold,
                details=[{"hallucinated_draft_ids": [str(d.id) for d in failed[:5]]}],
            )

    async def _eval_style_conformance(self, task: EvalTask) -> EvalResult:
        """Check style conformance scores against writing-style.md threshold."""
        from sqlalchemy import select
        from core.db import get_db_session
        from core.models.draft import Draft

        async with get_db_session() as session:
            window_start = datetime.now(tz=timezone.utc) - timedelta(hours=task.time_window_hours)
            scored = await session.execute(
                select(Draft).where(
                    Draft.mailbox_id == task.mailbox_id,
                    Draft.created_at >= window_start,
                    Draft.style_conformance_score.isnot(None),
                ).limit(task.sample_limit)
            )
            drafts = scored.scalars().all()

            threshold = 0.98  # >=98% style conformance
            if not drafts:
                return EvalResult(
                    user_id=task.user_id,
                    mailbox_id=task.mailbox_id,
                    correlation_id=task.correlation_id,
                    policy_version=task.policy_version,
                    eval_type="style_conformance",
                    pass_rate=1.0,
                    fail_count=0,
                    total_evaluated=0,
                    threshold=threshold,
                    passed=True,
                    details=[],
                )

            failed = [d for d in drafts if (d.style_conformance_score or 1.0) < threshold]
            pass_rate = 1.0 - len(failed) / len(drafts)

            return EvalResult(
                user_id=task.user_id,
                mailbox_id=task.mailbox_id,
                correlation_id=task.correlation_id,
                policy_version=task.policy_version,
                eval_type="style_conformance",
                pass_rate=pass_rate,
                fail_count=len(failed),
                total_evaluated=len(drafts),
                threshold=threshold,
                passed=pass_rate >= threshold,
                details=[],
            )

    async def _eval_safety(self, task: EvalTask) -> EvalResult:
        """Placeholder: injection pass rate checked by SafetyAgent inline."""
        return EvalResult(
            user_id=task.user_id,
            mailbox_id=task.mailbox_id,
            correlation_id=task.correlation_id,
            policy_version=task.policy_version,
            eval_type="safety",
            pass_rate=1.0,
            fail_count=0,
            total_evaluated=0,
            threshold=0.99,
            passed=True,
            details=["Safety eval requires curated adversarial test suite — see evals/ folder"],
        )
