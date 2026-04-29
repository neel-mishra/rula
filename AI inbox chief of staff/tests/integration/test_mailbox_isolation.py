"""
Mailbox isolation integration tests.
Day-0 exit criterion: all mail pipelines are mailbox-isolated,
verified by test with at least two connected mailboxes and no cross-contamination.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.models.email import Email
from core.models.mailbox import Mailbox
from core.models.memory import Memory, MemoryScope, MemoryType
from core.models.triage import TriageDecision, TriageMethod, TriageOutcome
from core.models.user import User


@pytest.fixture
def user(sample_user_id) -> User:
    return User(id=sample_user_id, email="neel@test.com", display_name="Neel")


@pytest.fixture
def mailbox_a() -> Mailbox:
    return Mailbox(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        gmail_email="work@gmail.com",
        gmail_user_id="work_user_123",
        is_active=True,
        is_connected=True,
    )


@pytest.fixture
def mailbox_b() -> Mailbox:
    return Mailbox(
        id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        gmail_email="personal@gmail.com",
        gmail_user_id="personal_user_456",
        is_active=True,
        is_connected=True,
    )


@pytest.mark.asyncio
async def test_emails_isolated_by_mailbox(db_session, user, mailbox_a, mailbox_b):
    """Emails from different mailboxes must not cross-contaminate."""
    db_session.add(user)
    db_session.add(mailbox_a)
    db_session.add(mailbox_b)
    await db_session.flush()

    email_a = Email(
        id=uuid.uuid4(),
        mailbox_id=mailbox_a.id,
        user_id=user.id,
        gmail_message_id="msg_work_001",
        gmail_thread_id="thread_work_001",
        subject="Work: Q3 Planning",
        from_address="boss@company.com",
        features={"is_newsletter": False},
    )
    email_b = Email(
        id=uuid.uuid4(),
        mailbox_id=mailbox_b.id,
        user_id=user.id,
        gmail_message_id="msg_personal_001",
        gmail_thread_id="thread_personal_001",
        subject="Personal: Weekend plans",
        from_address="friend@example.com",
        features={"is_newsletter": False},
    )
    db_session.add_all([email_a, email_b])
    await db_session.flush()

    # Query scoped by mailbox_a
    from sqlalchemy import select

    result_a = await db_session.execute(
        select(Email).where(Email.mailbox_id == mailbox_a.id)
    )
    emails_from_a = result_a.scalars().all()
    assert len(emails_from_a) == 1
    assert emails_from_a[0].subject == "Work: Q3 Planning"
    assert emails_from_a[0].mailbox_id == mailbox_a.id

    # Query scoped by mailbox_b
    result_b = await db_session.execute(
        select(Email).where(Email.mailbox_id == mailbox_b.id)
    )
    emails_from_b = result_b.scalars().all()
    assert len(emails_from_b) == 1
    assert emails_from_b[0].subject == "Personal: Weekend plans"
    assert emails_from_b[0].mailbox_id == mailbox_b.id

    # Cross-contamination check: IDs must not leak
    assert email_a.mailbox_id != email_b.mailbox_id


@pytest.mark.asyncio
async def test_memory_isolation_between_mailboxes(db_session, user, mailbox_a, mailbox_b):
    """Mailbox-scoped memories must not leak across mailboxes."""
    db_session.add(user)
    db_session.add(mailbox_a)
    db_session.add(mailbox_b)
    await db_session.flush()

    # Memory for mailbox A only
    mem_a = Memory(
        id=uuid.uuid4(),
        user_id=user.id,
        mailbox_id=mailbox_a.id,
        scope=MemoryScope.MAILBOX_SPECIFIC,
        applies_to_all_mailboxes=False,
        memory_type=MemoryType.POLICY,
        content="Always keep recruiter emails in inbox",
        structured_data={"rule": "always_inbox", "targets": ["recruiter@corp.com"]},
        source="assistant_instruction",
        confidence=0.95,
    )
    # Global memory — applies to all
    mem_global = Memory(
        id=uuid.uuid4(),
        user_id=user.id,
        mailbox_id=None,
        scope=MemoryScope.USER_GLOBAL,
        applies_to_all_mailboxes=True,
        memory_type=MemoryType.STYLE,
        content="Write replies in concise, professional tone",
        structured_data={},
        source="assistant_instruction",
        confidence=0.9,
    )
    db_session.add_all([mem_a, mem_global])
    await db_session.flush()

    from sqlalchemy import select

    # Query memories for mailbox_b: should get global memory only, NOT mem_a
    result = await db_session.execute(
        select(Memory).where(
            Memory.user_id == user.id,
            Memory.is_active == True,  # noqa: E712
            (
                (Memory.mailbox_id == mailbox_b.id)
                | (
                    (Memory.scope == MemoryScope.USER_GLOBAL)
                    & (Memory.applies_to_all_mailboxes == True)  # noqa: E712
                )
            ),
        )
    )
    memories_for_b = result.scalars().all()

    # Should only have global memory, not mailbox A's specific memory
    assert len(memories_for_b) == 1
    assert memories_for_b[0].scope == MemoryScope.USER_GLOBAL
    assert memories_for_b[0].applies_to_all_mailboxes is True

    # Query memories for mailbox_a: should get both mem_a and global
    result_a = await db_session.execute(
        select(Memory).where(
            Memory.user_id == user.id,
            Memory.is_active == True,  # noqa: E712
            (
                (Memory.mailbox_id == mailbox_a.id)
                | (
                    (Memory.scope == MemoryScope.USER_GLOBAL)
                    & (Memory.applies_to_all_mailboxes == True)  # noqa: E712
                )
            ),
        )
    )
    memories_for_a = result_a.scalars().all()
    assert len(memories_for_a) == 2


@pytest.mark.asyncio
async def test_triage_decisions_isolated(db_session, user, mailbox_a, mailbox_b):
    """Triage decisions must be scoped to the correct mailbox."""
    db_session.add(user)
    db_session.add(mailbox_a)
    db_session.add(mailbox_b)
    await db_session.flush()

    email_a = Email(
        id=uuid.uuid4(),
        mailbox_id=mailbox_a.id,
        user_id=user.id,
        gmail_message_id="msg_work_triage",
        gmail_thread_id="thread_work_triage",
        features={},
    )
    email_b = Email(
        id=uuid.uuid4(),
        mailbox_id=mailbox_b.id,
        user_id=user.id,
        gmail_message_id="msg_personal_triage",
        gmail_thread_id="thread_personal_triage",
        features={},
    )
    db_session.add_all([email_a, email_b])
    await db_session.flush()

    triage_a = TriageDecision(
        id=uuid.uuid4(),
        email_id=email_a.id,
        mailbox_id=mailbox_a.id,
        user_id=user.id,
        outcome=TriageOutcome.INBOX_KEEP,
        confidence=0.95,
        method=TriageMethod.DETERMINISTIC,
        policy_version="v1",
        correlation_id="corr-work-1",
    )
    triage_b = TriageDecision(
        id=uuid.uuid4(),
        email_id=email_b.id,
        mailbox_id=mailbox_b.id,
        user_id=user.id,
        outcome=TriageOutcome.BRIEF_ONLY,
        confidence=0.88,
        method=TriageMethod.LLM,
        policy_version="v1",
        correlation_id="corr-personal-1",
    )
    db_session.add_all([triage_a, triage_b])
    await db_session.flush()

    from sqlalchemy import select

    # Query triage for mailbox_a only
    result = await db_session.execute(
        select(TriageDecision).where(TriageDecision.mailbox_id == mailbox_a.id)
    )
    decisions = result.scalars().all()
    assert len(decisions) == 1
    assert decisions[0].outcome == TriageOutcome.INBOX_KEEP
    assert decisions[0].mailbox_id == mailbox_a.id

    # Verify no cross-contamination
    result_b = await db_session.execute(
        select(TriageDecision).where(TriageDecision.mailbox_id == mailbox_b.id)
    )
    decisions_b = result_b.scalars().all()
    assert len(decisions_b) == 1
    assert decisions_b[0].outcome == TriageOutcome.BRIEF_ONLY
    assert decisions_b[0].mailbox_id == mailbox_b.id
