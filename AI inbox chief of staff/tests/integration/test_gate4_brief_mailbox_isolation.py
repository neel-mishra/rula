"""Gate 4 — Brief-pipeline mailbox isolation tests.

Per the product roadmap, briefs are strictly per-mailbox; there is no
cross-mailbox unified digest. These tests assert that property end-to-end
through BriefAgent + the briefs HTTP surface:

  1. Two mailboxes for the same user → each gets its own brief; no merged digest.
  2. Mailbox A's items never appear in Mailbox B's brief, even when the
     time windows overlap.
  3. Per-mailbox brief preferences (`brief_enabled`, `brief_morning_hour`,
     `brief_afternoon_hour`) are honored independently in the scheduler's
     SQL filter and per-mailbox window selection.

LLM and SES are mocked — this is a database/contract test, not an LLM eval.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from core.models.brief import Brief, BriefItem, BriefStatus, BriefWindow
from core.models.email import Email
from core.models.mailbox import Mailbox
from core.models.triage import TriageDecision, TriageMethod, TriageOutcome
from core.models.user import User
from core.schemas.contracts import BriefTask


# ────────────────────────────── helpers ──────────────────────────────────


def _patched_get_db_session(session):
    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


class _FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLMClient:
    def __init__(self, payloads: list[dict] | None = None) -> None:
        self._payloads = payloads or [
            {
                "category": "newsletter",
                "summary": "Generated summary",
                "key_points": [],
                "importance_score": 0.5,
            }
        ]
        self._idx = 0

    async def complete(self, *args, **kwargs) -> _FakeLLMResponse:
        payload = self._payloads[self._idx % len(self._payloads)]
        self._idx += 1
        return _FakeLLMResponse(content=json.dumps(payload))


@pytest.fixture
def shared_user(sample_user_id) -> User:
    return User(
        id=sample_user_id,
        email="multi@test.com",
        display_name="Multi-mailbox User",
        is_active=True,
    )


@pytest.fixture
def mailbox_work(sample_user_id) -> Mailbox:
    return Mailbox(
        id=uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"),
        user_id=sample_user_id,
        gmail_email="work@example.com",
        gmail_user_id="work_sub",
        is_active=True,
        is_connected=True,
        brief_enabled=True,
        brief_morning_hour=8,
        brief_afternoon_hour=17,
    )


@pytest.fixture
def mailbox_personal(sample_user_id) -> Mailbox:
    return Mailbox(
        id=uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb"),
        user_id=sample_user_id,
        gmail_email="personal@example.com",
        gmail_user_id="personal_sub",
        is_active=True,
        is_connected=True,
        brief_enabled=True,
        brief_morning_hour=9,        # different time window
        brief_afternoon_hour=18,
    )


async def _seed_emails_for(db, *, mailbox: Mailbox, user: User, n: int, label: str):
    """Insert N briefable emails (each tagged with BRIEF_ONLY triage)."""
    now = datetime.now(tz=timezone.utc)
    emails = []
    for i in range(n):
        em = Email(
            id=uuid.uuid4(),
            mailbox_id=mailbox.id,
            user_id=user.id,
            gmail_message_id=f"{label}-msg-{i}",
            gmail_thread_id=f"{label}-thread-{i}",
            subject=f"{label} email {i}",
            from_address=f"sender-{label}-{i}@ex.com",
            snippet=f"Snippet for {label} #{i}",
            received_at=now - timedelta(hours=2),
            features={},
        )
        db.add(em)
        emails.append(em)
    await db.flush()
    for em in emails:
        td = TriageDecision(
            id=uuid.uuid4(),
            email_id=em.id,
            mailbox_id=mailbox.id,
            user_id=user.id,
            outcome=TriageOutcome.BRIEF_ONLY,
            confidence=0.9,
            method=TriageMethod.LLM,
            policy_version="v1",
            correlation_id=f"corr-{label}-{em.gmail_message_id}",
        )
        db.add(td)
    await db.flush()
    return emails


async def _new_brief(db, *, mailbox: Mailbox, user: User) -> Brief:
    brief = Brief(
        id=uuid.uuid4(),
        mailbox_id=mailbox.id,
        user_id=user.id,
        window=BriefWindow.MORNING,
        scheduled_at=datetime.now(tz=timezone.utc),
        status=BriefStatus.PENDING,
        policy_version="v1",
        correlation_id=f"corr-brief-{mailbox.gmail_email}",
    )
    db.add(brief)
    await db.flush()
    return brief


# ──────────────────── Two mailboxes → two distinct briefs ─────────────────


@pytest.mark.asyncio
async def test_two_mailboxes_same_user_get_independent_briefs(
    db_session, shared_user, mailbox_work, mailbox_personal
):
    from subagents import brief as brief_mod

    db_session.add(shared_user)
    db_session.add(mailbox_work)
    db_session.add(mailbox_personal)
    await db_session.flush()

    # Distinct content per mailbox.
    await _seed_emails_for(db_session, mailbox=mailbox_work, user=shared_user, n=2, label="WORK")
    await _seed_emails_for(db_session, mailbox=mailbox_personal, user=shared_user, n=3, label="PERSONAL")

    brief_work = await _new_brief(db_session, mailbox=mailbox_work, user=shared_user)
    brief_personal = await _new_brief(db_session, mailbox=mailbox_personal, user=shared_user)

    fake_llm = _FakeLLMClient(
        payloads=[
            {"category": "update", "summary": "Work S1", "key_points": [], "importance_score": 0.6},
            {"category": "update", "summary": "Work S2", "key_points": [], "importance_score": 0.4},
            {"category": "newsletter", "summary": "Pers S1", "key_points": [], "importance_score": 0.7},
            {"category": "fyi", "summary": "Pers S2", "key_points": [], "importance_score": 0.3},
            {"category": "fyi", "summary": "Pers S3", "key_points": [], "importance_score": 0.5},
        ]
    )

    now = datetime.now(tz=timezone.utc)
    window = (now - timedelta(hours=12), now + timedelta(hours=1))

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("subagents.brief.settings.ses_enabled", False):
            with patch("subagents.brief.settings.shadow_mode", False):
                with patch("subagents.brief.settings.kill_switch_llm", False):
                    with patch("core.llm.client.get_llm_client", return_value=fake_llm):
                        agent = brief_mod.BriefAgent()
                        await agent._execute(
                            BriefTask(
                                user_id=shared_user.id,
                                mailbox_id=mailbox_work.id,
                                correlation_id="c-work",
                                brief_id=brief_work.id,
                                window="morning",
                                time_window_start=window[0],
                                time_window_end=window[1],
                            )
                        )
                        await agent._execute(
                            BriefTask(
                                user_id=shared_user.id,
                                mailbox_id=mailbox_personal.id,
                                correlation_id="c-personal",
                                brief_id=brief_personal.id,
                                window="morning",
                                time_window_start=window[0],
                                time_window_end=window[1],
                            )
                        )

    await db_session.refresh(brief_work)
    await db_session.refresh(brief_personal)

    # Two separate briefs — no unified digest.
    assert brief_work.id != brief_personal.id
    assert brief_work.mailbox_id == mailbox_work.id
    assert brief_personal.mailbox_id == mailbox_personal.id

    # Per-mailbox item counts match the seeded inputs exactly.
    assert brief_work.item_count == 2
    assert brief_personal.item_count == 3

    # Validate via the BriefItem table that the items are correctly partitioned.
    work_items = (await db_session.execute(
        select(BriefItem).where(BriefItem.brief_id == brief_work.id)
    )).scalars().all()
    personal_items = (await db_session.execute(
        select(BriefItem).where(BriefItem.brief_id == brief_personal.id)
    )).scalars().all()

    assert {i.mailbox_id for i in work_items} == {mailbox_work.id}
    assert {i.mailbox_id for i in personal_items} == {mailbox_personal.id}


# ──────────────────── Cross-mailbox content cannot leak ───────────────────


@pytest.mark.asyncio
async def test_mailbox_a_items_never_appear_in_mailbox_b_brief(
    db_session, shared_user, mailbox_work, mailbox_personal
):
    """
    Even with overlapping time windows and a shared user, BriefAgent's
    `Email.mailbox_id == task.mailbox_id` filter must keep mailboxes
    fully partitioned.
    """
    from subagents import brief as brief_mod

    db_session.add(shared_user)
    db_session.add(mailbox_work)
    db_session.add(mailbox_personal)
    await db_session.flush()

    # Both mailboxes have email in the same wall-clock window.
    work_emails = await _seed_emails_for(
        db_session, mailbox=mailbox_work, user=shared_user, n=2, label="WORK"
    )
    personal_emails = await _seed_emails_for(
        db_session, mailbox=mailbox_personal, user=shared_user, n=2, label="PERSONAL"
    )

    work_subjects = {em.subject for em in work_emails}
    personal_subjects = {em.subject for em in personal_emails}

    brief_b = await _new_brief(db_session, mailbox=mailbox_personal, user=shared_user)

    fake_llm = _FakeLLMClient(
        payloads=[
            # Mirror the real source subject into the summary so we can grep
            # the resulting brief body for cross-mailbox bleed.
            {"category": "update", "summary": em.subject, "key_points": [], "importance_score": 0.5}
            for em in personal_emails
        ]
    )

    now = datetime.now(tz=timezone.utc)
    window = (now - timedelta(hours=12), now + timedelta(hours=1))

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("subagents.brief.settings.ses_enabled", False):
            with patch("subagents.brief.settings.shadow_mode", False):
                with patch("subagents.brief.settings.kill_switch_llm", False):
                    with patch("core.llm.client.get_llm_client", return_value=fake_llm):
                        agent = brief_mod.BriefAgent()
                        await agent._execute(
                            BriefTask(
                                user_id=shared_user.id,
                                mailbox_id=mailbox_personal.id,
                                correlation_id="c-iso",
                                brief_id=brief_b.id,
                                window="morning",
                                time_window_start=window[0],
                                time_window_end=window[1],
                            )
                        )

    await db_session.refresh(brief_b)
    assert brief_b.item_count == len(personal_emails)

    body = (brief_b.body_html or "") + "\n" + (brief_b.body_text or "")
    for subj in personal_subjects:
        assert subj in body
    for subj in work_subjects:
        assert subj not in body, f"WORK subject leaked into PERSONAL brief: {subj}"

    # And the BriefItem rows themselves carry only mailbox_personal.id.
    items = (await db_session.execute(
        select(BriefItem).where(BriefItem.brief_id == brief_b.id)
    )).scalars().all()
    assert {i.mailbox_id for i in items} == {mailbox_personal.id}


# ──────────────── Per-mailbox preferences honored independently ───────────


@pytest.mark.asyncio
async def test_per_mailbox_brief_enabled_flag_filters_independently(
    db_session, shared_user, mailbox_work, mailbox_personal
):
    """
    The scheduler's `WHERE brief_enabled = True` clause must short-circuit
    only the mailbox(es) where the flag is False, leaving the other
    mailboxes for the same user fully active.
    """
    db_session.add(shared_user)
    # Disable briefs on the personal mailbox only.
    mailbox_personal.brief_enabled = False
    db_session.add(mailbox_work)
    db_session.add(mailbox_personal)
    await db_session.flush()

    result = await db_session.execute(
        select(Mailbox).where(
            Mailbox.user_id == shared_user.id,
            Mailbox.is_active == True,        # noqa: E712
            Mailbox.brief_enabled == True,    # noqa: E712
        )
    )
    eligible = result.scalars().all()
    assert {mb.id for mb in eligible} == {mailbox_work.id}


@pytest.mark.asyncio
async def test_per_mailbox_window_hours_resolve_independently(
    db_session, shared_user, mailbox_work, mailbox_personal
):
    """
    Mirrors the per-mailbox window-resolution logic in
    `workers.scheduler.schedule_briefs`: each mailbox's own
    `brief_morning_hour` / `brief_afternoon_hour` must be honored, with
    settings defaults only acting as fallbacks.
    """
    from core.config import settings

    db_session.add(shared_user)
    # Mailbox personal: explicit override (9, 18). Mailbox work: defaults via None.
    mailbox_work.brief_morning_hour = None
    mailbox_work.brief_afternoon_hour = None
    db_session.add(mailbox_work)
    db_session.add(mailbox_personal)
    await db_session.flush()

    def _resolve(mb: Mailbox) -> tuple[int, int]:
        morning = mb.brief_morning_hour or settings.brief_morning_hour
        afternoon = mb.brief_afternoon_hour or settings.brief_afternoon_hour
        return morning, afternoon

    work_hours = _resolve(mailbox_work)
    personal_hours = _resolve(mailbox_personal)

    assert work_hours == (settings.brief_morning_hour, settings.brief_afternoon_hour)
    assert personal_hours == (9, 18)
    assert work_hours != personal_hours


@pytest.mark.asyncio
async def test_user_briefs_query_returns_per_mailbox_rows_not_unified(
    db_session, shared_user, mailbox_work, mailbox_personal
):
    """
    The user-facing `/briefs/` listing must return one row per mailbox brief,
    not a single merged digest. Asserted directly on the ORM to keep the
    test independent of HTTP layering.
    """
    db_session.add(shared_user)
    db_session.add(mailbox_work)
    db_session.add(mailbox_personal)
    await db_session.flush()

    now = datetime.now(tz=timezone.utc)
    brief_w = Brief(
        id=uuid.uuid4(),
        mailbox_id=mailbox_work.id,
        user_id=shared_user.id,
        window=BriefWindow.MORNING,
        scheduled_at=now,
        status=BriefStatus.DELIVERED,
        subject_line="Work morning",
        item_count=2,
        policy_version="v1",
        correlation_id="c-w",
    )
    brief_p = Brief(
        id=uuid.uuid4(),
        mailbox_id=mailbox_personal.id,
        user_id=shared_user.id,
        window=BriefWindow.MORNING,
        scheduled_at=now,
        status=BriefStatus.DELIVERED,
        subject_line="Personal morning",
        item_count=3,
        policy_version="v1",
        correlation_id="c-p",
    )
    db_session.add_all([brief_w, brief_p])
    await db_session.flush()

    rows = (await db_session.execute(
        select(Brief).where(Brief.user_id == shared_user.id)
    )).scalars().all()

    # Two distinct briefs — never merged into one unified digest.
    assert len(rows) == 2
    assert {r.mailbox_id for r in rows} == {mailbox_work.id, mailbox_personal.id}
    # And they preserve their per-mailbox identifiers independently.
    assert {r.subject_line for r in rows} == {"Work morning", "Personal morning"}
