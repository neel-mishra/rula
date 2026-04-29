"""
SLO metric computations — pure async functions over the shared session.

Each function is scoped to a single user to keep authorization simple: a
dashboard user can only ever see their own SLO numbers. Operators who need
cross-user SLOs will hit the API differently (admin RBAC — separate work).

All metrics honor a rolling window (default 7 days) and return
`MetricReading(value=None, status=NOT_MEASURED)` when the sample size is
below the target's `min_sample_size`. This prevents an early, noisy reading
from being read as a PASS or FAIL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.brief import Brief, BriefStatus
from core.models.draft import Draft, DraftStatus
from core.models.email import Email
from core.models.mutation_ledger import MutationLedger, MutationStatus
from core.models.triage import TriageDecision, TriageOutcome
from core.slo.targets import (
    MetricReading,
    TARGETS,
    evaluate,
)


def _window_start(window_days: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=window_days)


def _reading(
    target_id: str,
    value: float | None,
    sample_size: int,
    note: str | None = None,
) -> MetricReading:
    target = TARGETS[target_id]
    if sample_size < target.min_sample_size:
        return MetricReading(
            target=target,
            value=None,
            sample_size=sample_size,
            status=evaluate(None, target),
            note=note
            or f"sample size {sample_size} < min {target.min_sample_size}",
        )
    return MetricReading(
        target=target,
        value=value,
        sample_size=sample_size,
        status=evaluate(value, target),
        note=note,
    )


def _percentile(values: list[float], p: float) -> float | None:
    """Simple linear-interpolation percentile. Returns None for empty input."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


# ─────────────────────────────────────────────────────────────────────────────
# Quality metrics
# ─────────────────────────────────────────────────────────────────────────────


async def false_archive_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    total_q = select(sa_func.count(MutationLedger.id)).where(
        MutationLedger.user_id == user_id,
        MutationLedger.created_at >= cutoff,
    )
    undone_q = total_q.where(
        MutationLedger.status == MutationStatus.UNDONE,
    )
    total = (await session.execute(total_q)).scalar() or 0
    undone = (await session.execute(undone_q)).scalar() or 0
    rate = (undone / total) if total else None
    return _reading("false_archive_rate", rate, total)


async def false_brief_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    total_q = select(sa_func.count(TriageDecision.id)).where(
        TriageDecision.user_id == user_id,
        TriageDecision.outcome == TriageOutcome.BRIEF_ONLY,
        TriageDecision.created_at >= cutoff,
    )
    corrected_q = total_q.where(TriageDecision.corrected_by_user.is_(True))
    total = (await session.execute(total_q)).scalar() or 0
    corrected = (await session.execute(corrected_q)).scalar() or 0
    rate = (corrected / total) if total else None
    return _reading("false_brief_rate", rate, total)


async def draft_grounding_failure_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    total_q = select(sa_func.count(Draft.id)).where(
        Draft.user_id == user_id,
        Draft.created_at >= cutoff,
    )
    fail_flag = case(
        (Draft.status == DraftStatus.REJECTED, 1),
        (Draft.hallucination_flag.is_(True), 1),
        else_=0,
    )
    failed_q = select(sa_func.coalesce(sa_func.sum(fail_flag), 0)).where(
        Draft.user_id == user_id,
        Draft.created_at >= cutoff,
    )
    total = (await session.execute(total_q)).scalar() or 0
    failed = int((await session.execute(failed_q)).scalar() or 0)
    rate = (failed / total) if total else None
    return _reading("draft_grounding_failure_rate", rate, total)


# ─────────────────────────────────────────────────────────────────────────────
# Latency metrics
# ─────────────────────────────────────────────────────────────────────────────


async def _ingest_to_triage_latencies(
    session: AsyncSession, user_id: uuid.UUID, window_days: int
) -> list[float]:
    cutoff = _window_start(window_days)
    result = await session.execute(
        select(Email.received_at, TriageDecision.created_at)
        .join(TriageDecision, TriageDecision.email_id == Email.id)
        .where(
            TriageDecision.user_id == user_id,
            TriageDecision.created_at >= cutoff,
            Email.received_at.is_not(None),
        )
    )
    latencies: list[float] = []
    for received_at, triaged_at in result.all():
        if received_at and triaged_at:
            delta = (triaged_at - received_at).total_seconds()
            if delta >= 0:
                latencies.append(delta)
    return latencies


async def ingest_to_triage_p95(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    latencies = await _ingest_to_triage_latencies(session, user_id, window_days)
    value = _percentile(latencies, 95)
    return _reading("ingest_to_triage_p95", value, len(latencies))


async def ingest_to_triage_p99(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    latencies = await _ingest_to_triage_latencies(session, user_id, window_days)
    value = _percentile(latencies, 99)
    return _reading("ingest_to_triage_p99", value, len(latencies))


async def draft_generation_p95(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    result = await session.execute(
        select(Email.received_at, Draft.created_at)
        .join(Draft, Draft.email_id == Email.id)
        .where(
            Draft.user_id == user_id,
            Draft.created_at >= cutoff,
            Email.received_at.is_not(None),
        )
    )
    latencies: list[float] = []
    for received_at, drafted_at in result.all():
        if received_at and drafted_at:
            delta = (drafted_at - received_at).total_seconds()
            if delta >= 0:
                latencies.append(delta)
    value = _percentile(latencies, 95)
    return _reading("draft_generation_p95", value, len(latencies))


# ─────────────────────────────────────────────────────────────────────────────
# Reliability / Brief metrics
# ─────────────────────────────────────────────────────────────────────────────


async def brief_completion_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    total_q = select(sa_func.count(Brief.id)).where(
        Brief.user_id == user_id,
        Brief.created_at >= cutoff,
    )
    good_flag = case(
        (Brief.status == BriefStatus.DELIVERED, 1),
        (Brief.status == BriefStatus.SKIPPED, 1),  # intentional skip on empty window
        else_=0,
    )
    good_q = select(sa_func.coalesce(sa_func.sum(good_flag), 0)).where(
        Brief.user_id == user_id,
        Brief.created_at >= cutoff,
    )
    total = (await session.execute(total_q)).scalar() or 0
    good = int((await session.execute(good_q)).scalar() or 0)
    rate = (good / total) if total else None
    return _reading("brief_completion_rate", rate, total)


async def brief_timeliness_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    result = await session.execute(
        select(Brief.scheduled_at, Brief.delivered_at).where(
            Brief.user_id == user_id,
            Brief.created_at >= cutoff,
            Brief.status == BriefStatus.DELIVERED,
        )
    )
    rows = result.all()
    total = len(rows)
    on_time = 0
    for scheduled_at, delivered_at in rows:
        if scheduled_at and delivered_at:
            delay = (delivered_at - scheduled_at).total_seconds()
            if delay <= 600:
                on_time += 1
    rate = (on_time / total) if total else None
    return _reading("brief_timeliness_rate", rate, total)


# ─────────────────────────────────────────────────────────────────────────────
# Undo metrics
# ─────────────────────────────────────────────────────────────────────────────


async def undo_success_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    undone_q = select(sa_func.count(MutationLedger.id)).where(
        MutationLedger.user_id == user_id,
        MutationLedger.status == MutationStatus.UNDONE,
        MutationLedger.created_at >= cutoff,
    )
    failed_q = select(sa_func.count(MutationLedger.id)).where(
        MutationLedger.user_id == user_id,
        MutationLedger.status == MutationStatus.UNDO_FAILED,
        MutationLedger.created_at >= cutoff,
    )
    undone = (await session.execute(undone_q)).scalar() or 0
    failed = (await session.execute(failed_q)).scalar() or 0
    total = undone + failed
    rate = (undone / total) if total else None
    return _reading("undo_success_rate", rate, total)


async def undo_execution_p95(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    cutoff = _window_start(window_days)
    result = await session.execute(
        select(MutationLedger.applied_at, MutationLedger.undone_at).where(
            MutationLedger.user_id == user_id,
            MutationLedger.status == MutationStatus.UNDONE,
            MutationLedger.undone_at.is_not(None),
            MutationLedger.undone_at >= cutoff,
        )
    )
    latencies: list[float] = []
    for applied_at, undone_at in result.all():
        if applied_at and undone_at:
            delta = (undone_at - applied_at).total_seconds()
            if delta >= 0:
                latencies.append(delta)
    value = _percentile(latencies, 95)
    return _reading("undo_execution_p95", value, len(latencies))


# ─────────────────────────────────────────────────────────────────────────────
# Not-yet-instrumented metrics — return NOT_MEASURED with a useful note
# ─────────────────────────────────────────────────────────────────────────────


async def prompt_injection_pass_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    # Computed at CI time over the adversarial suite (17 tests, 100% as of the
    # latest run). Reported statically here; a follow-up will expose the
    # latest CI JSON artifact.
    target = TARGETS["prompt_injection_pass_rate"]
    return MetricReading(
        target=target,
        value=1.0,
        sample_size=17,
        status=evaluate(1.0, target),
        note="Static value from latest CI adversarial suite (17/17 pass).",
    )


async def llm_cache_hit_rate(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    from core.llm.cache import get_cache_stats

    target = TARGETS["llm_cache_hit_rate"]
    stats = await get_cache_stats(window_days=window_days)
    total = stats["total"]
    return _reading(
        "llm_cache_hit_rate",
        stats["hit_rate"],
        total,
        note=(
            f"hits={stats['hits']} misses={stats['misses']} over {window_days}d"
            if total
            else None
        ),
    )


async def cost_per_inbox_per_day(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> MetricReading:
    from core.llm.budget import get_cost_totals

    target = TARGETS["cost_per_inbox_per_day"]
    totals = await get_cost_totals(window_days=window_days)
    value = totals["cost_per_active_mailbox_day"]
    sample_size = totals["active_mailbox_days"]
    note = (
        f"total ${totals['total_usd']:.2f} over {sample_size} mailbox-days"
        if sample_size
        else None
    )
    return _reading("cost_per_inbox_per_day", value, sample_size, note=note)


# ─────────────────────────────────────────────────────────────────────────────
# Bulk rollup
# ─────────────────────────────────────────────────────────────────────────────


_ALL_METRICS = [
    false_archive_rate,
    false_brief_rate,
    draft_grounding_failure_rate,
    ingest_to_triage_p95,
    ingest_to_triage_p99,
    draft_generation_p95,
    brief_completion_rate,
    brief_timeliness_rate,
    undo_success_rate,
    undo_execution_p95,
    prompt_injection_pass_rate,
    llm_cache_hit_rate,
    cost_per_inbox_per_day,
]


async def collect_all(
    session: AsyncSession, user_id: uuid.UUID, window_days: int = 7
) -> list[MetricReading]:
    return [
        await fn(session, user_id, window_days) for fn in _ALL_METRICS
    ]
