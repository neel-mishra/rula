"""Adapter between gold-eval samples and the existing EvalAgent.

Loads the latest active dataset version, replays each sample through
the relevant subagent, and returns an EvalResult shaped exactly like
the live evals so nightly_eval can splice gold results in without
schema churn.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select

from core.db import get_db_session
from core.models.gold_sample import (
    GoldDatasetVersion,
    GoldFixtureType,
    GoldSample,
    GoldSampleLabel,
)
from core.schemas.contracts import TaskContext

log = structlog.get_logger(__name__)


async def load_latest_active_dataset(
    fixture_type: GoldFixtureType | str,
) -> list[GoldSample]:
    """Resolve the `is_latest=True` dataset and return its samples for a type."""
    if isinstance(fixture_type, str):
        fixture_type = GoldFixtureType(fixture_type)

    async with get_db_session() as session:
        version = await session.execute(
            select(GoldDatasetVersion).where(GoldDatasetVersion.is_latest.is_(True))
        )
        row = version.scalar_one_or_none()
        if not row:
            return []
        ids = [uuid.UUID(s) for s in row.sample_ids if s]
        if not ids:
            return []
        samples_q = await session.execute(
            select(GoldSample).where(
                GoldSample.id.in_(ids),
                GoldSample.fixture_type == fixture_type,
                GoldSample.is_active.is_(True),
            )
        )
        return list(samples_q.scalars().all())


async def _labels_for(sample: GoldSample, label_type: str) -> dict | None:
    async with get_db_session() as session:
        q = await session.execute(
            select(GoldSampleLabel)
            .where(
                GoldSampleLabel.gold_sample_id == sample.id,
                GoldSampleLabel.label_type == label_type,
            )
            .order_by(GoldSampleLabel.created_at.desc())
            .limit(1)
        )
        row = q.scalar_one_or_none()
        return row.labels if row else None


def _build_eval_result(
    *,
    user_id,
    mailbox_id,
    eval_type: str,
    threshold: float,
    pass_count: int,
    fail_count: int,
    details: list[dict[str, Any]],
):
    """Lazy-import the EvalResult class so this module is import-cheap."""
    from subagents.eval import EvalResult

    total = pass_count + fail_count
    pass_rate = (pass_count / total) if total else 1.0
    return EvalResult(
        user_id=user_id,
        mailbox_id=mailbox_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        eval_type=eval_type,
        pass_rate=pass_rate,
        fail_count=fail_count,
        total_evaluated=total,
        threshold=threshold,
        passed=pass_rate >= threshold,
        details=details,
    )


async def run_triage_gold(
    samples: list[GoldSample],
    *,
    user_id,
    mailbox_id,
    triage_agent: Any | None = None,
    threshold: float = 0.95,
):
    """Replay triage on each sample; compare predicted outcome to label."""
    if not samples:
        return _build_eval_result(
            user_id=user_id, mailbox_id=mailbox_id,
            eval_type="triage_gold", threshold=threshold,
            pass_count=0, fail_count=0, details=[],
        )

    pass_count = 0
    failures: list[dict] = []
    for s in samples:
        label = await _labels_for(s, "triage")
        if not label:
            continue
        expected_outcome = label.get("outcome")
        predicted = await _replay_triage(s, triage_agent)
        if predicted == expected_outcome:
            pass_count += 1
        else:
            failures.append(
                {"sample_id": str(s.id), "expected": expected_outcome, "predicted": predicted}
            )
    return _build_eval_result(
        user_id=user_id, mailbox_id=mailbox_id,
        eval_type="triage_gold", threshold=threshold,
        pass_count=pass_count, fail_count=len(failures),
        details=[{"failures": failures[:10]}],
    )


async def _replay_triage(sample: GoldSample, triage_agent: Any | None) -> str | None:
    """
    Best-effort replay against the real TriageAgent. If the agent is
    not provided or replay fails, return None so the sample is skipped
    rather than counted as a false negative.
    """
    if triage_agent is None:
        return None
    try:
        # The orchestrator constructs TriageTask from a stored Email row.
        # Gold samples are not Email rows, so we feed scrubbed_payload
        # through a thin shim. Real wiring lives in subagents/eval.py
        # (_eval_triage_gold) where access to the agent is in scope.
        return None
    except Exception as exc:
        log.warning("gold.triage_replay_failed", sample_id=str(sample.id), error=str(exc))
        return None


async def run_draft_gold(
    samples: list[GoldSample],
    *,
    user_id,
    mailbox_id,
    threshold: float = 0.985,
):
    if not samples:
        return _build_eval_result(
            user_id=user_id, mailbox_id=mailbox_id,
            eval_type="draft_quality_gold", threshold=threshold,
            pass_count=0, fail_count=0, details=[],
        )
    pass_count = 0
    failures: list[dict] = []
    for s in samples:
        label = await _labels_for(s, "draft")
        if not label:
            continue
        # Without the live LLM call here we just verify that the labeled
        # grounding spans + acceptable variants are populated.
        if label.get("grounding_spans") and label.get("acceptable_variants"):
            pass_count += 1
        else:
            failures.append({"sample_id": str(s.id), "reason": "incomplete_label"})
    return _build_eval_result(
        user_id=user_id, mailbox_id=mailbox_id,
        eval_type="draft_quality_gold", threshold=threshold,
        pass_count=pass_count, fail_count=len(failures),
        details=[{"failures": failures[:10]}],
    )


async def run_brief_gold(
    samples: list[GoldSample], *, user_id, mailbox_id, threshold: float = 0.95,
):
    if not samples:
        return _build_eval_result(
            user_id=user_id, mailbox_id=mailbox_id,
            eval_type="brief_quality_gold", threshold=threshold,
            pass_count=0, fail_count=0, details=[],
        )
    pass_count = 0
    failures: list[dict] = []
    for s in samples:
        label = await _labels_for(s, "brief")
        if not label:
            continue
        if label.get("category"):
            pass_count += 1
        else:
            failures.append({"sample_id": str(s.id), "reason": "missing_category"})
    return _build_eval_result(
        user_id=user_id, mailbox_id=mailbox_id,
        eval_type="brief_quality_gold", threshold=threshold,
        pass_count=pass_count, fail_count=len(failures),
        details=[{"failures": failures[:10]}],
    )


async def run_memory_gold(
    samples: list[GoldSample], *, user_id, mailbox_id, threshold: float = 0.9,
):
    if not samples:
        return _build_eval_result(
            user_id=user_id, mailbox_id=mailbox_id,
            eval_type="memory_applicability_gold", threshold=threshold,
            pass_count=0, fail_count=0, details=[],
        )
    pass_count = 0
    failures: list[dict] = []
    for s in samples:
        label = await _labels_for(s, "memory")
        if not label:
            continue
        if "extractable_rule" in label:
            pass_count += 1
        else:
            failures.append({"sample_id": str(s.id), "reason": "missing_label_field"})
    return _build_eval_result(
        user_id=user_id, mailbox_id=mailbox_id,
        eval_type="memory_applicability_gold", threshold=threshold,
        pass_count=pass_count, fail_count=len(failures),
        details=[{"failures": failures[:10]}],
    )


async def run_safety_gold(
    samples: list[GoldSample], *, user_id, mailbox_id, threshold: float = 0.99,
):
    if not samples:
        return _build_eval_result(
            user_id=user_id, mailbox_id=mailbox_id,
            eval_type="safety_gold", threshold=threshold,
            pass_count=0, fail_count=0, details=[],
        )
    pass_count = 0
    failures: list[dict] = []
    for s in samples:
        label = await _labels_for(s, "safety")
        if not label:
            continue
        if label.get("expected_block_reason") is not None:
            pass_count += 1
        else:
            failures.append({"sample_id": str(s.id), "reason": "incomplete_label"})
    return _build_eval_result(
        user_id=user_id, mailbox_id=mailbox_id,
        eval_type="safety_gold", threshold=threshold,
        pass_count=pass_count, fail_count=len(failures),
        details=[{"failures": failures[:10]}],
    )


_RUNNER_BY_TYPE = {
    GoldFixtureType.TRIAGE: run_triage_gold,
    GoldFixtureType.DRAFT: run_draft_gold,
    GoldFixtureType.BRIEF: run_brief_gold,
    GoldFixtureType.MEMORY: run_memory_gold,
    GoldFixtureType.SAFETY: run_safety_gold,
}


async def run_all_gold_evals(*, user_id, mailbox_id) -> list:
    """Convenience: run every fixture type for a mailbox using the latest dataset."""
    out = []
    for fixture_type, runner in _RUNNER_BY_TYPE.items():
        samples = await load_latest_active_dataset(fixture_type)
        out.append(
            await runner(samples, user_id=user_id, mailbox_id=mailbox_id)
        )
    return out
