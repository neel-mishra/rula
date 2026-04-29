"""Integration tests for SLO metric queries against seeded data."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from core.models.brief import Brief, BriefStatus, BriefWindow
from core.models.draft import Draft, DraftStatus
from core.models.email import Email
from core.models.mailbox import Mailbox
from core.models.mutation_ledger import (
    MutationLedger,
    MutationStatus,
    MutationType,
)
from core.models.triage import TriageDecision, TriageMethod, TriageOutcome
from core.slo import MetricStatus
from core.slo.metrics import (
    brief_completion_rate,
    brief_timeliness_rate,
    collect_all,
    draft_generation_p95,
    draft_grounding_failure_rate,
    false_archive_rate,
    false_brief_rate,
    ingest_to_triage_p95,
    undo_execution_p95,
    undo_success_rate,
)


USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MAILBOX_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _seed_mailbox(session) -> None:
    from core.models.user import User
    # Reset to a known state — the `db_session` fixture rolls back after the test
    existing_user = await session.get(User, USER_ID)
    if existing_user is None:
        session.add(User(
            id=USER_ID, email="slo@test", display_name="SLO", is_active=True,
        ))
    existing_mb = await session.get(Mailbox, MAILBOX_ID)
    if existing_mb is None:
        session.add(Mailbox(
            id=MAILBOX_ID,
            user_id=USER_ID,
            gmail_email="slo@test",
            gmail_user_id="slo-user",
            is_active=True,
            is_connected=True,
        ))
    await session.flush()


async def _add_email(session, *, received_offset_seconds: int) -> uuid.UUID:
    email_id = uuid.uuid4()
    session.add(Email(
        id=email_id,
        mailbox_id=MAILBOX_ID,
        user_id=USER_ID,
        gmail_message_id=f"msg-{email_id.hex[:8]}",
        gmail_thread_id=f"th-{email_id.hex[:8]}",
        received_at=_now() - timedelta(seconds=received_offset_seconds),
    ))
    await session.flush()
    return email_id


async def _add_triage(
    session,
    email_id: uuid.UUID,
    *,
    outcome: TriageOutcome,
    corrected: bool = False,
    latency_s: float = 30.0,
) -> None:
    session.add(TriageDecision(
        id=uuid.uuid4(),
        email_id=email_id,
        mailbox_id=MAILBOX_ID,
        user_id=USER_ID,
        outcome=outcome,
        confidence=0.85,
        method=TriageMethod.LLM,
        policy_version="v1",
        corrected_by_user=corrected,
        correlation_id=str(uuid.uuid4()),
    ))
    await session.flush()


async def _add_mutation(
    session,
    email_id: uuid.UUID,
    *,
    status: MutationStatus,
) -> None:
    now = _now()
    session.add(MutationLedger(
        id=uuid.uuid4(),
        email_id=email_id,
        mailbox_id=MAILBOX_ID,
        user_id=USER_ID,
        mutation_type=MutationType.ARCHIVE,
        status=status,
        prior_state={"labels": ["INBOX"]},
        new_state={"labels": []},
        reason_trace="test",
        policy_version="v1",
        undo_token=f"tok-{uuid.uuid4().hex[:12]}",
        undo_expires_at=now + timedelta(days=7),
        applied_at=now - timedelta(seconds=60),
        undone_at=now if status == MutationStatus.UNDONE else None,
        correlation_id=str(uuid.uuid4()),
    ))
    await session.flush()


async def _add_draft(
    session,
    email_id: uuid.UUID,
    *,
    status: DraftStatus = DraftStatus.GENERATED,
    grounding: float | None = 0.9,
    hallucination: bool = False,
) -> None:
    session.add(Draft(
        id=uuid.uuid4(),
        email_id=email_id,
        mailbox_id=MAILBOX_ID,
        user_id=USER_ID,
        draft_text="hi",
        prompt_version="v1",
        model_id="test",
        policy_version="v1",
        grounding_score=grounding,
        hallucination_flag=hallucination,
        status=status,
        correlation_id=str(uuid.uuid4()),
    ))
    await session.flush()


async def _add_brief(
    session,
    *,
    status: BriefStatus,
    scheduled_offset_seconds: int = 0,
    delivery_delay_seconds: float | None = 60,
) -> None:
    now = _now()
    scheduled_at = now - timedelta(seconds=scheduled_offset_seconds)
    delivered_at = (
        scheduled_at + timedelta(seconds=delivery_delay_seconds)
        if delivery_delay_seconds is not None
        else None
    )
    session.add(Brief(
        id=uuid.uuid4(),
        mailbox_id=MAILBOX_ID,
        user_id=USER_ID,
        window=BriefWindow.MORNING,
        scheduled_at=scheduled_at,
        delivered_at=delivered_at,
        status=status,
        policy_version="v1",
        correlation_id=str(uuid.uuid4()),
    ))
    await session.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Quality metrics
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_false_archive_rate_below_min_sample(db_session):
    await _seed_mailbox(db_session)
    reading = await false_archive_rate(db_session, USER_ID)
    assert reading.status is MetricStatus.NOT_MEASURED
    assert reading.sample_size == 0


@pytest.mark.asyncio
async def test_false_archive_rate_passes_with_low_undo(db_session):
    await _seed_mailbox(db_session)
    # 10 mutations, 0 undone -> 0%
    for _ in range(10):
        email_id = await _add_email(db_session, received_offset_seconds=120)
        await _add_mutation(db_session, email_id, status=MutationStatus.APPLIED)
    reading = await false_archive_rate(db_session, USER_ID)
    assert reading.status is MetricStatus.PASS
    assert reading.value == 0.0
    assert reading.sample_size == 10


@pytest.mark.asyncio
async def test_false_archive_rate_fails_when_many_undone(db_session):
    await _seed_mailbox(db_session)
    # 10 mutations, 3 undone -> 30% >> 0.5% target
    for i in range(10):
        email_id = await _add_email(db_session, received_offset_seconds=120)
        status = MutationStatus.UNDONE if i < 3 else MutationStatus.APPLIED
        await _add_mutation(db_session, email_id, status=status)
    reading = await false_archive_rate(db_session, USER_ID)
    assert reading.status is MetricStatus.FAIL
    assert reading.value == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_false_brief_rate(db_session):
    await _seed_mailbox(db_session)
    # 20 brief decisions; 2 corrected -> 10%
    for i in range(20):
        email_id = await _add_email(db_session, received_offset_seconds=60)
        await _add_triage(
            db_session, email_id,
            outcome=TriageOutcome.BRIEF_ONLY,
            corrected=(i < 2),
        )
    reading = await false_brief_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(0.10)
    assert reading.status is MetricStatus.FAIL


@pytest.mark.asyncio
async def test_draft_grounding_failure_rate(db_session):
    await _seed_mailbox(db_session)
    # 10 drafts; 1 rejected, 1 halluc-flagged -> 20% (fail)
    for i in range(10):
        email_id = await _add_email(db_session, received_offset_seconds=60)
        if i == 0:
            await _add_draft(db_session, email_id, status=DraftStatus.REJECTED)
        elif i == 1:
            await _add_draft(db_session, email_id, hallucination=True)
        else:
            await _add_draft(db_session, email_id)
    reading = await draft_grounding_failure_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(0.20)
    assert reading.status is MetricStatus.FAIL


# ─────────────────────────────────────────────────────────────────────────────
# Latency metrics
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_to_triage_p95(db_session):
    await _seed_mailbox(db_session)
    # Seed 10 emails received_at = now - 30s, triage is implicitly now -> ~30s latency
    for _ in range(10):
        email_id = await _add_email(db_session, received_offset_seconds=30)
        await _add_triage(db_session, email_id, outcome=TriageOutcome.INBOX_KEEP)
    reading = await ingest_to_triage_p95(db_session, USER_ID)
    assert reading.value is not None
    # Should be comfortably within 60s target
    assert reading.value < 60.0
    assert reading.status is MetricStatus.PASS


@pytest.mark.asyncio
async def test_draft_generation_p95(db_session):
    await _seed_mailbox(db_session)
    for _ in range(10):
        email_id = await _add_email(db_session, received_offset_seconds=20)
        await _add_draft(db_session, email_id)
    reading = await draft_generation_p95(db_session, USER_ID)
    assert reading.value is not None
    assert reading.value < 45.0
    assert reading.status is MetricStatus.PASS


# ─────────────────────────────────────────────────────────────────────────────
# Brief metrics
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_brief_completion_rate_delivered_and_skipped_both_count(db_session):
    await _seed_mailbox(db_session)
    for _ in range(8):
        await _add_brief(db_session, status=BriefStatus.DELIVERED)
    for _ in range(2):
        await _add_brief(db_session, status=BriefStatus.SKIPPED)
    reading = await brief_completion_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(1.0)
    assert reading.status is MetricStatus.PASS


@pytest.mark.asyncio
async def test_brief_completion_rate_fails_with_many_failures(db_session):
    await _seed_mailbox(db_session)
    # 3 delivered, 7 failed -> 0.3, well below 0.995 target band.
    for _ in range(3):
        await _add_brief(db_session, status=BriefStatus.DELIVERED)
    for _ in range(7):
        await _add_brief(db_session, status=BriefStatus.FAILED)
    reading = await brief_completion_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(0.3)
    assert reading.status is MetricStatus.FAIL


@pytest.mark.asyncio
async def test_brief_timeliness_rate_counts_within_10_min(db_session):
    await _seed_mailbox(db_session)
    # 4 delivered inside 10min, 1 delivered at 20min
    for _ in range(4):
        await _add_brief(
            db_session,
            status=BriefStatus.DELIVERED,
            delivery_delay_seconds=120,
        )
    await _add_brief(
        db_session,
        status=BriefStatus.DELIVERED,
        delivery_delay_seconds=1200,   # 20 min → late
    )
    reading = await brief_timeliness_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(0.8)


# ─────────────────────────────────────────────────────────────────────────────
# Undo metrics
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_undo_success_rate_fails_far_below_target(db_session):
    # Target 0.999 with a 0.1998 warn band → FAIL below ~0.799
    await _seed_mailbox(db_session)
    for _ in range(5):
        email_id = await _add_email(db_session, received_offset_seconds=60)
        await _add_mutation(db_session, email_id, status=MutationStatus.UNDONE)
    for _ in range(5):
        email_id = await _add_email(db_session, received_offset_seconds=60)
        await _add_mutation(
            db_session, email_id, status=MutationStatus.UNDO_FAILED,
        )
    reading = await undo_success_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(0.5)
    assert reading.status is MetricStatus.FAIL


@pytest.mark.asyncio
async def test_undo_execution_p95_measured(db_session):
    # Target 30s; seed mutations where applied_at - undone_at ≈ 5s → PASS.
    await _seed_mailbox(db_session)
    now = _now()
    for _ in range(10):
        email_id = await _add_email(db_session, received_offset_seconds=60)
        db_session.add(MutationLedger(
            id=uuid.uuid4(),
            email_id=email_id,
            mailbox_id=MAILBOX_ID,
            user_id=USER_ID,
            mutation_type=MutationType.ARCHIVE,
            status=MutationStatus.UNDONE,
            prior_state={"labels": ["INBOX"]},
            new_state={"labels": []},
            reason_trace="test",
            policy_version="v1",
            undo_token=f"tok-{uuid.uuid4().hex[:12]}",
            undo_expires_at=now + timedelta(days=7),
            applied_at=now - timedelta(seconds=5),
            undone_at=now,
            correlation_id=str(uuid.uuid4()),
        ))
    await db_session.flush()
    reading = await undo_execution_p95(db_session, USER_ID)
    assert reading.value is not None
    assert reading.value <= 10.0
    assert reading.status is MetricStatus.PASS


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slo_status_endpoint_shape(authenticated_client: AsyncClient):
    resp = await authenticated_client.get("/slo/status")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["window_days"] == 7
    assert len(data["metrics"]) >= 13
    assert set(data["summary"].keys()) == {"pass", "warn", "fail", "not_measured"}
    # Critical metrics all present with a status
    ids = {m["id"] for m in data["metrics"]}
    assert {"false_archive_rate", "prompt_injection_pass_rate", "undo_success_rate"} <= ids


@pytest.mark.asyncio
async def test_collect_all_fans_out(db_session):
    await _seed_mailbox(db_session)
    readings = await collect_all(db_session, USER_ID)
    assert len(readings) >= 13
    # Prompt-injection is a static pass; always populated
    ids = {r.target.id for r in readings}
    assert "prompt_injection_pass_rate" in ids
    injection = next(
        r for r in readings if r.target.id == "prompt_injection_pass_rate"
    )
    assert injection.status is MetricStatus.PASS
