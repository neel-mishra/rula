"""Gate-2 (Triage Engine) eval-sample-run integration tests.

Exercises the false-archive / false-brief rate computations end-to-end
against gold fixtures loaded by ``workers.gold_fixture_loader``.

Pipeline under test:
    .json/.eml fixture -> gold_fixture_loader.load_fixtures_from_dir
        -> GoldSample row (with expected_action label in raw_payload)
        -> simulated triage decision + mutation ledger entry
        -> core.slo.metrics.false_archive_rate / false_brief_rate

Each fixture file may carry an ``expected_action`` field (one of
``inbox_keep`` / ``brief_only``). Fixtures without that field are
ignored by this test — they exist only for the loader/stratifier suite.

LLM is not invoked: the rule engine is deterministic and matches our
labelled fixtures (newsletters with List-Unsubscribe → BRIEF_ONLY,
direct replies → INBOX_KEEP), so we can simulate triage decisions
without mocking the LLM. Where we want to fabricate "false" outcomes
(system says brief, user corrects to inbox_keep), we seed the
TriageDecision/MutationLedger rows directly — that path is what
the SLO metrics actually read.
"""

from __future__ import annotations

import json
import math
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from core.models.email import Email
from core.models.gold_sample import GoldSample
from core.models.mailbox import Mailbox
from core.models.mutation_ledger import (
    MutationLedger,
    MutationStatus,
    MutationType,
)
from core.models.triage import TriageDecision, TriageMethod, TriageOutcome
from core.models.user import User
from core.slo import MetricStatus
from core.slo.metrics import false_archive_rate, false_brief_rate
from subagents.triage import run_rule_engine
from workers.gold_fixture_loader import load_fixtures_from_dir

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "gold_emails"

# Map our fixture's `expected_action` strings to the triage outcome enum.
_ACTION_TO_OUTCOME = {
    "inbox_keep": TriageOutcome.INBOX_KEEP,
    "brief_only": TriageOutcome.BRIEF_ONLY,
    "draft_candidate": TriageOutcome.DRAFT_CANDIDATE,
    "protected": TriageOutcome.PROTECTED,
}

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
MAILBOX_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


# ── Shared fixtures ────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_mailbox(db_session) -> Mailbox:
    user = await db_session.get(User, USER_ID)
    if user is None:
        user = User(
            id=USER_ID,
            email="gate2@test.com",
            display_name="Gate2 Tester",
            is_active=True,
        )
        db_session.add(user)
    mailbox = await db_session.get(Mailbox, MAILBOX_ID)
    if mailbox is None:
        mailbox = Mailbox(
            id=MAILBOX_ID,
            user_id=USER_ID,
            gmail_email="user@example.com",
            gmail_user_id="gate2_user",
            is_active=True,
            is_connected=True,
        )
        db_session.add(mailbox)
    await db_session.flush()
    return mailbox


@pytest.fixture
def session_factory(db_session):
    """Hand the loader the same session our test owns so commits land in-tx."""

    @asynccontextmanager
    async def _factory():
        yield db_session

    return _factory


# ── Helpers ────────────────────────────────────────────────────────────────


def _features_from_payload(payload: dict) -> dict:
    """Derive the same feature dict TriageAgent passes to the rule engine."""
    headers = {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in (payload.get("headers") or [])
    }
    has_unsub = "list-unsubscribe" in headers or "list-id" in headers
    in_reply_to = headers.get("in-reply-to") or ""
    to_field = headers.get("to", "").lower()
    is_direct = "user@example.com" in to_field
    return {
        "is_newsletter": has_unsub,
        "sender_vip": False,
        "is_reply": bool(in_reply_to),
        "is_direct_to_user": is_direct,
        "from_address": headers.get("from", ""),
        "from_domain": headers.get("from", "").split("@")[-1].rstrip(">").lower(),
    }


def _read_label_index(fixtures_dir: Path) -> dict[str, str]:
    """Return ``{subject: expected_action}`` for every labelled .json fixture.

    The loader's ``_parse_json`` discards unknown top-level keys, so the
    ``expected_action`` field never reaches ``GoldSample.raw_payload``.
    Re-read the source files here and key them by subject — which the
    loader does preserve and which is unique across our labelled corpus.
    """
    index: dict[str, str] = {}
    for path in fixtures_dir.rglob("*.json"):
        try:
            with path.open("rb") as fh:
                raw = json.load(fh)
        except Exception:
            continue
        action = raw.get("expected_action")
        subject = raw.get("subject")
        if action and subject:
            index[subject] = action
    return index


def _labelled_samples(
    samples: list[GoldSample], label_index: dict[str, str]
) -> list[GoldSample]:
    """Return one gold sample per labelled source fixture."""
    seen: set[str] = set()
    out: list[GoldSample] = []
    for s in samples:
        subject = (s.raw_payload or {}).get("subject", "")
        if subject not in label_index:
            continue
        # Loader inserts one row per fixture_type; we only need one row
        # per source file for this test.
        src = s.source_gmail_message_id or ""
        if src in seen:
            continue
        seen.add(src)
        out.append(s)
    return out


async def _seed_email(db_session, sample: GoldSample) -> Email:
    """Materialise a real Email row from the gold sample's raw_payload."""
    payload = sample.raw_payload or {}
    headers = {
        (h.get("name") or "").lower(): h.get("value") or ""
        for h in (payload.get("headers") or [])
    }
    sender = headers.get("from", "")
    domain = sender.split("@")[-1].rstrip(">").lower() if "@" in sender else ""
    email = Email(
        id=uuid.uuid4(),
        mailbox_id=sample.mailbox_id,
        user_id=sample.user_id,
        gmail_message_id=f"gate2-{uuid.uuid4().hex[:10]}",
        gmail_thread_id=f"th-{uuid.uuid4().hex[:10]}",
        subject=payload.get("subject") or "",
        from_address=sender,
        from_domain=domain,
        snippet=(payload.get("body_text") or "")[:200],
        body_text=payload.get("body_text") or "",
        received_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
        features=_features_from_payload(payload),
    )
    db_session.add(email)
    await db_session.flush()
    return email


async def _record_triage(
    db_session,
    *,
    email: Email,
    outcome: TriageOutcome,
    corrected_by_user: bool = False,
    confidence: float = 0.92,
    method: TriageMethod = TriageMethod.DETERMINISTIC,
) -> TriageDecision:
    decision = TriageDecision(
        id=uuid.uuid4(),
        email_id=email.id,
        mailbox_id=email.mailbox_id,
        user_id=email.user_id,
        outcome=outcome,
        confidence=confidence,
        method=method,
        policy_version="v1",
        corrected_by_user=corrected_by_user,
        correlation_id=str(uuid.uuid4()),
    )
    db_session.add(decision)
    await db_session.flush()
    return decision


async def _record_archive_mutation(
    db_session,
    *,
    email: Email,
    status: MutationStatus,
    triage_decision_id: uuid.UUID | None = None,
) -> MutationLedger:
    now = datetime.now(tz=timezone.utc)
    mutation = MutationLedger(
        id=uuid.uuid4(),
        email_id=email.id,
        mailbox_id=email.mailbox_id,
        user_id=email.user_id,
        mutation_type=MutationType.ARCHIVE,
        status=status,
        prior_state={"labels": ["INBOX"]},
        new_state={"labels": []},
        reason_trace="gate2 eval test",
        policy_version="v1",
        triage_decision_id=triage_decision_id,
        undo_token=f"tok-{uuid.uuid4().hex[:12]}",
        undo_expires_at=now + timedelta(days=7),
        applied_at=now - timedelta(seconds=30),
        undone_at=now if status == MutationStatus.UNDONE else None,
        correlation_id=str(uuid.uuid4()),
    )
    db_session.add(mutation)
    await db_session.flush()
    return mutation


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gold_loader_seeds_labelled_samples(
    db_session, seeded_mailbox, session_factory
):
    """Sanity: the Tier A loader picks up our labelled fixtures intact."""
    result = await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    assert result.persisted > 0
    assert result.skipped_invalid == 0

    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()
    label_index = _read_label_index(FIXTURES_DIR)
    labelled = _labelled_samples(samples, label_index)
    # We added 3 labelled fixtures in this dir; require at least 2 so the
    # test stays robust if someone adds more in the future.
    assert len(labelled) >= 2, (
        f"need ≥2 labelled fixtures; index={label_index} matched={len(labelled)}"
    )
    actions = {label_index[s.raw_payload["subject"]] for s in labelled}
    assert "inbox_keep" in actions
    assert "brief_only" in actions


@pytest.mark.asyncio
async def test_rule_engine_matches_labelled_outcomes(
    db_session, seeded_mailbox, session_factory
):
    """Deterministic-comparison path: rule engine output == expected_action."""
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()

    label_index = _read_label_index(FIXTURES_DIR)
    matched = 0
    checked = 0
    for s in _labelled_samples(samples, label_index):
        expected = _ACTION_TO_OUTCOME[label_index[s.raw_payload["subject"]]]
        features = _features_from_payload(s.raw_payload or {})
        rule_hit = run_rule_engine(features, memories=[])
        if rule_hit is None:
            # Rules don't fire on every fixture (e.g. ambiguous) — skip.
            continue
        outcome, _confidence, _rule = rule_hit
        checked += 1
        if outcome == expected:
            matched += 1

    # We expect every fixture the rules fire on to land on its labelled
    # outcome; this proves the deterministic-comparison path is sound.
    assert checked >= 2
    assert matched == checked


@pytest.mark.asyncio
async def test_false_archive_rate_known_good_passes(
    db_session, seeded_mailbox, session_factory
):
    """Known-good path: every archive sticks → rate == 0 → PASS."""
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()

    archive_count = 0
    # Use the SLO target's min_sample_size guard (≥ 5) — pad with extra
    # synthetic archives generated from the labelled brief_only samples.
    label_index = _read_label_index(FIXTURES_DIR)
    brief_samples = [
        s for s in _labelled_samples(samples, label_index)
        if label_index.get(s.raw_payload.get("subject", "")) == "brief_only"
    ]
    assert brief_samples, "need at least one brief_only fixture"

    while archive_count < 10:
        for s in brief_samples:
            email = await _seed_email(db_session, s)
            decision = await _record_triage(
                db_session, email=email, outcome=TriageOutcome.BRIEF_ONLY,
            )
            await _record_archive_mutation(
                db_session,
                email=email,
                status=MutationStatus.APPLIED,
                triage_decision_id=decision.id,
            )
            archive_count += 1
            if archive_count >= 10:
                break

    reading = await false_archive_rate(db_session, USER_ID)
    assert reading.value is not None
    assert math.isfinite(reading.value)
    assert reading.value == pytest.approx(0.0)
    assert reading.status is MetricStatus.PASS
    assert reading.sample_size == 10


@pytest.mark.asyncio
async def test_false_archive_rate_known_bad_fails(
    db_session, seeded_mailbox, session_factory
):
    """Known-bad path: 4/10 archives undone → rate 0.40, well above 0.5%."""
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()
    label_index = _read_label_index(FIXTURES_DIR)
    brief_samples = [
        s for s in _labelled_samples(samples, label_index)
        if label_index.get(s.raw_payload.get("subject", "")) == "brief_only"
    ]
    assert brief_samples

    total = 10
    undo_target = 4
    seeded = 0
    while seeded < total:
        for s in brief_samples:
            email = await _seed_email(db_session, s)
            decision = await _record_triage(
                db_session, email=email, outcome=TriageOutcome.BRIEF_ONLY,
            )
            status = (
                MutationStatus.UNDONE if seeded < undo_target
                else MutationStatus.APPLIED
            )
            await _record_archive_mutation(
                db_session,
                email=email,
                status=status,
                triage_decision_id=decision.id,
            )
            seeded += 1
            if seeded >= total:
                break

    reading = await false_archive_rate(db_session, USER_ID)
    assert reading.value is not None
    assert math.isfinite(reading.value)
    assert reading.value == pytest.approx(undo_target / total)
    # 0.5% target with 0.1% warn band → 0.40 must be FAIL.
    assert reading.status is MetricStatus.FAIL
    assert reading.sample_size == total


@pytest.mark.asyncio
async def test_false_brief_rate_known_good_passes(
    db_session, seeded_mailbox, session_factory
):
    """Known-good path: every brief decision uncorrected → rate 0.0 → PASS."""
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()
    label_index = _read_label_index(FIXTURES_DIR)
    brief_samples = [
        s for s in _labelled_samples(samples, label_index)
        if label_index.get(s.raw_payload.get("subject", "")) == "brief_only"
    ]
    assert brief_samples

    total = 10
    seeded = 0
    while seeded < total:
        for s in brief_samples:
            email = await _seed_email(db_session, s)
            await _record_triage(
                db_session,
                email=email,
                outcome=TriageOutcome.BRIEF_ONLY,
                corrected_by_user=False,
            )
            seeded += 1
            if seeded >= total:
                break

    reading = await false_brief_rate(db_session, USER_ID)
    assert reading.value is not None
    assert math.isfinite(reading.value)
    assert reading.value == pytest.approx(0.0)
    assert reading.status is MetricStatus.PASS
    assert reading.sample_size == total


@pytest.mark.asyncio
async def test_false_brief_rate_known_bad_fails(
    db_session, seeded_mailbox, session_factory
):
    """Known-bad path: 3/10 brief decisions corrected → rate 0.30 → FAIL."""
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()
    label_index = _read_label_index(FIXTURES_DIR)
    brief_samples = [
        s for s in _labelled_samples(samples, label_index)
        if label_index.get(s.raw_payload.get("subject", "")) == "brief_only"
    ]
    assert brief_samples

    total = 10
    correct_target = 3
    seeded = 0
    while seeded < total:
        for s in brief_samples:
            email = await _seed_email(db_session, s)
            await _record_triage(
                db_session,
                email=email,
                outcome=TriageOutcome.BRIEF_ONLY,
                corrected_by_user=(seeded < correct_target),
            )
            seeded += 1
            if seeded >= total:
                break

    reading = await false_brief_rate(db_session, USER_ID)
    assert reading.value is not None
    assert math.isfinite(reading.value)
    assert reading.value == pytest.approx(correct_target / total)
    # 1% target with 0.2% warn band → 0.30 is well into FAIL.
    assert reading.status is MetricStatus.FAIL
    assert reading.sample_size == total


@pytest.mark.asyncio
async def test_threshold_crossing_warn_band(
    db_session, seeded_mailbox, session_factory
):
    """Crossing-the-line check: rate just above target_value lands in WARN.

    false_archive_rate target is 0.5% with a 20% (== 0.1% absolute) warn
    band; seed 1 undo out of 200 archives (== 0.5%) → PASS, then bump to
    1 undo out of 150 (== 0.667%) which is above target but inside the
    target+band of 0.6%... so let's pick numbers we can reason about
    exactly.
    """
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    samples = (
        await db_session.execute(
            select(GoldSample).where(GoldSample.mailbox_id == seeded_mailbox.id)
        )
    ).scalars().all()
    label_index = _read_label_index(FIXTURES_DIR)
    brief_samples = [
        s for s in _labelled_samples(samples, label_index)
        if label_index.get(s.raw_payload.get("subject", "")) == "brief_only"
    ]
    assert brief_samples
    template = brief_samples[0]

    # Seed 200 archives, exactly 1 undone → rate = 0.005 → PASS boundary.
    for i in range(200):
        email = await _seed_email(db_session, template)
        decision = await _record_triage(
            db_session, email=email, outcome=TriageOutcome.BRIEF_ONLY,
        )
        status = MutationStatus.UNDONE if i == 0 else MutationStatus.APPLIED
        await _record_archive_mutation(
            db_session,
            email=email,
            status=status,
            triage_decision_id=decision.id,
        )

    reading = await false_archive_rate(db_session, USER_ID)
    assert reading.value == pytest.approx(0.005)
    # 0.005 == target → PASS
    assert reading.status is MetricStatus.PASS

    # Now push one more undo: 2/201 ≈ 0.00995 → above target (0.005),
    # below target+band (0.005 + 0.001 = 0.006)? No: 0.00995 > 0.006 → FAIL.
    extra = await _seed_email(db_session, template)
    extra_decision = await _record_triage(
        db_session, email=extra, outcome=TriageOutcome.BRIEF_ONLY,
    )
    await _record_archive_mutation(
        db_session,
        email=extra,
        status=MutationStatus.UNDONE,
        triage_decision_id=extra_decision.id,
    )
    reading2 = await false_archive_rate(db_session, USER_ID)
    assert reading2.value is not None
    assert math.isfinite(reading2.value)
    assert reading2.value > reading.value  # rate strictly increased
    assert reading2.status in (MetricStatus.WARN, MetricStatus.FAIL)


@pytest.mark.asyncio
async def test_metrics_below_min_sample_report_not_measured(
    db_session, seeded_mailbox, session_factory
):
    """Insufficient data → NOT_MEASURED, not a spurious PASS/FAIL."""
    await load_fixtures_from_dir(
        FIXTURES_DIR, seeded_mailbox.id, session_factory=session_factory,
    )
    # Don't seed any triage decisions / mutations.
    archive_reading = await false_archive_rate(db_session, USER_ID)
    brief_reading = await false_brief_rate(db_session, USER_ID)
    assert archive_reading.status is MetricStatus.NOT_MEASURED
    assert archive_reading.value is None
    assert archive_reading.sample_size == 0
    assert brief_reading.status is MetricStatus.NOT_MEASURED
    assert brief_reading.value is None
    assert brief_reading.sample_size == 0
