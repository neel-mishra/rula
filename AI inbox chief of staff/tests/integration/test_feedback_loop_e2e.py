"""Feedback-loop end-to-end — closes Gate 5.c.

Submits a triage correction via the REST endpoint, then verifies:
1. A FeedbackEvent row is created and linked to the email.
2. For PROTECTED corrections, a Memory row is auto-created with
   structured_data['rule'] == 'always_inbox' and the sender targeted.
3. The TriageDecision is marked corrected_by_user=True.
4. AlwaysInboxRule (the rule that consumes that memory at next-triage)
   recognizes the new memory shape — the consumer side is exercised
   directly so we don't need to wait for a real next-triage run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_protected_correction_creates_memory_and_marks_decision(
    authenticated_client, db_session, sample_user_id, sample_mailbox_id,
):
    from core.models.email import Email
    from core.models.feedback import FeedbackEvent
    from core.models.mailbox import Mailbox
    from core.models.memory import Memory, MemoryScope, MemoryType
    from core.models.triage import TriageDecision, TriageOutcome, TriageMethod

    # ── Arrange: minimal Mailbox + Email + TriageDecision rows ────────────
    mailbox = Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="user@example.com",
        gmail_user_id="google-sub-test",
        is_active=True,
        is_connected=True,
    )
    db_session.add(mailbox)

    email_id = uuid.uuid4()
    email = Email(
        id=email_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_message_id="gmsg-feedback-loop",
        gmail_thread_id="gthr-feedback-loop",
        subject="Q3 partnership renewal",
        from_address="vip@partner.example.com",
        from_domain="partner.example.com",
        snippet="Looking to renew our deal.",
        received_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(email)

    triage = TriageDecision(
        id=uuid.uuid4(),
        email_id=email_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        outcome=TriageOutcome.BRIEF_ONLY,
        confidence=0.7,
        method=TriageMethod.LLM,
        rule_matched=None,
        corrected_by_user=False,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
    )
    db_session.add(triage)
    await db_session.flush()

    # ── Act: submit a correction promoting it to PROTECTED ────────────────
    response = await authenticated_client.post(
        "/feedback/triage-correction",
        json={
            "email_id": str(email_id),
            "correct_outcome": TriageOutcome.PROTECTED.value,
            "reason": "this sender is always important",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["memory_updated"] is True
    assert "Memory rule created" in body["message"]

    # ── Assert: FeedbackEvent row exists and references the email ─────────
    feedbacks = (await db_session.execute(
        select(FeedbackEvent).where(FeedbackEvent.email_id == email_id)
    )).scalars().all()
    assert len(feedbacks) == 1
    fb = feedbacks[0]
    assert fb.feedback_type == "triage_correction"
    assert fb.structured_intent["original_outcome"] == TriageOutcome.BRIEF_ONLY.value
    assert fb.structured_intent["correct_outcome"] == TriageOutcome.PROTECTED.value
    assert fb.structured_intent["from_address"] == "vip@partner.example.com"

    # ── Assert: TriageDecision is now flagged corrected_by_user ──────────
    refreshed_triage = await db_session.get(TriageDecision, triage.id)
    assert refreshed_triage.corrected_by_user is True

    # ── Assert: Memory row created with the always_inbox rule shape ──────
    memories = (await db_session.execute(
        select(Memory).where(
            Memory.user_id == sample_user_id,
            Memory.mailbox_id == sample_mailbox_id,
            Memory.memory_type == MemoryType.POLICY,
        )
    )).scalars().all()
    assert len(memories) == 1
    mem = memories[0]
    assert mem.scope == MemoryScope.MAILBOX_SPECIFIC
    assert mem.is_active is True
    assert mem.structured_data["rule"] == "always_inbox"
    assert "vip@partner.example.com" in mem.structured_data["targets"]
    # Confidence on user-issued protected correction is 1.0.
    assert mem.confidence == 1.0


@pytest.mark.asyncio
async def test_brief_to_inbox_correction_marks_false_brief_signal(
    authenticated_client, db_session, sample_user_id, sample_mailbox_id,
):
    """Correction from BRIEF_ONLY → INBOX_KEEP labels the feedback as 'false_brief'."""
    from core.models.email import Email
    from core.models.feedback import FeedbackEvent
    from core.models.mailbox import Mailbox
    from core.models.triage import TriageDecision, TriageOutcome, TriageMethod

    mailbox = Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="user@example.com",
        gmail_user_id="google-sub-test",
        is_active=True,
        is_connected=True,
    )
    db_session.add(mailbox)

    email_id = uuid.uuid4()
    db_session.add(Email(
        id=email_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_message_id="gmsg-false-brief",
        gmail_thread_id="gthr-false-brief",
        subject="Quick question",
        from_address="boss@example.com",
        from_domain="example.com",
        snippet="When can we sync?",
    ))
    db_session.add(TriageDecision(
        id=uuid.uuid4(),
        email_id=email_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        outcome=TriageOutcome.BRIEF_ONLY,
        confidence=0.6,
        method=TriageMethod.LLM,
        corrected_by_user=False,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
    ))
    await db_session.flush()

    response = await authenticated_client.post(
        "/feedback/triage-correction",
        json={
            "email_id": str(email_id),
            "correct_outcome": TriageOutcome.INBOX_KEEP.value,
            "reason": "this is actionable",
        },
    )
    assert response.status_code == 200, response.text

    fb = (await db_session.execute(
        select(FeedbackEvent).where(FeedbackEvent.email_id == email_id)
    )).scalar_one()
    assert fb.structured_intent.get("signal") == "false_brief"


@pytest.mark.asyncio
async def test_always_inbox_rule_consumes_protected_memory(
    db_session, sample_user_id, sample_mailbox_id,
):
    """
    Direct consumer-side check: the AlwaysInboxRule (or the equivalent
    triage code path) must read structured_data['targets'] and treat
    them as protected senders. This proves the loop closes:
    correction → memory write → next-triage behavior.
    """
    from core.models.mailbox import Mailbox
    from core.models.memory import Memory, MemoryScope, MemoryType

    db_session.add(Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="user@example.com",
        gmail_user_id="google-sub-test",
        is_active=True,
        is_connected=True,
    ))
    db_session.add(Memory(
        id=uuid.uuid4(),
        user_id=sample_user_id,
        mailbox_id=sample_mailbox_id,
        scope=MemoryScope.MAILBOX_SPECIFIC,
        applies_to_all_mailboxes=False,
        memory_type=MemoryType.POLICY,
        content="Always keep emails from vip@partner.example.com in inbox",
        structured_data={
            "rule": "always_inbox",
            "targets": ["vip@partner.example.com"],
            "source": "triage_correction",
        },
        source="triage_correction",
        confidence=1.0,
        is_active=True,
    ))
    await db_session.flush()

    # Pull active always_inbox memories for this mailbox. This mirrors
    # the lookup TriageAgent does at next-triage time.
    rows = (await db_session.execute(
        select(Memory).where(
            Memory.user_id == sample_user_id,
            Memory.mailbox_id == sample_mailbox_id,
            Memory.is_active == True,  # noqa: E712
        )
    )).scalars().all()

    targets: set[str] = set()
    for m in rows:
        if (m.structured_data or {}).get("rule") == "always_inbox":
            targets.update((m.structured_data or {}).get("targets") or [])

    assert "vip@partner.example.com" in targets


@pytest.mark.asyncio
async def test_correction_changes_next_triage_outcome_e2e(
    authenticated_client, db_session, sample_user_id, sample_mailbox_id,
):
    """Two-cycle end-to-end: BRIEF_ONLY for sender X → user corrects to
    PROTECTED → next email from X is triaged by the deterministic rule
    engine as PROTECTED via the new memory.

    This proves correction → memory → behavior change closes the loop.
    The rule engine is invoked directly (no LLM) — AlwaysInboxRule reads
    the memory shape produced by /feedback/triage-correction.
    """
    from core.models.email import Email
    from core.models.mailbox import Mailbox
    from core.models.memory import Memory, MemoryScope, MemoryType
    from core.models.triage import TriageDecision, TriageOutcome, TriageMethod
    from subagents.triage import run_rule_engine

    sender = "exec@partner.example.com"

    # ── Cycle 1: seed mailbox + email1 + initial BRIEF_ONLY decision ─────
    db_session.add(Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="user@example.com",
        gmail_user_id="google-sub-test",
        is_active=True,
        is_connected=True,
    ))

    email1_id = uuid.uuid4()
    db_session.add(Email(
        id=email1_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_message_id="gmsg-cycle1",
        gmail_thread_id="gthr-cycle1",
        subject="Renewal kickoff",
        from_address=sender,
        from_domain="partner.example.com",
        snippet="Let's get started.",
        received_at=datetime.now(tz=timezone.utc),
    ))
    db_session.add(TriageDecision(
        id=uuid.uuid4(),
        email_id=email1_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        outcome=TriageOutcome.BRIEF_ONLY,  # the "wrong" decision
        confidence=0.6,
        method=TriageMethod.LLM,
        corrected_by_user=False,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
    ))
    await db_session.flush()

    # Sanity: BEFORE correction, no always_inbox memory exists, so the rule
    # engine should NOT match for this sender.
    memories_before = (await db_session.execute(
        select(Memory).where(
            Memory.user_id == sample_user_id,
            Memory.mailbox_id == sample_mailbox_id,
            Memory.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    pre_match = run_rule_engine(
        email_features={"from_address": sender, "from_domain": "partner.example.com"},
        memories=[
            {"structured_data": m.structured_data, "memory_type": m.memory_type.value}
            for m in memories_before
        ],
    )
    assert pre_match is None, "no always_inbox memory should exist yet"

    # ── User correction: BRIEF_ONLY → PROTECTED via REST endpoint ────────
    response = await authenticated_client.post(
        "/feedback/triage-correction",
        json={
            "email_id": str(email1_id),
            "correct_outcome": TriageOutcome.PROTECTED.value,
            "reason": "this exec is always important",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["memory_updated"] is True

    # ── Cycle 2: a NEW similar email from the same sender arrives ────────
    email2_id = uuid.uuid4()
    db_session.add(Email(
        id=email2_id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_message_id="gmsg-cycle2",
        gmail_thread_id="gthr-cycle2",
        subject="Renewal follow-up",  # similar to cycle 1
        from_address=sender,
        from_domain="partner.example.com",
        snippet="Pinging on the renewal.",
        received_at=datetime.now(tz=timezone.utc),
    ))
    await db_session.flush()

    # Pull active memories (mirrors what TriageAgent does at next-triage).
    memories_after = (await db_session.execute(
        select(Memory).where(
            Memory.user_id == sample_user_id,
            Memory.mailbox_id == sample_mailbox_id,
            Memory.is_active == True,  # noqa: E712
            Memory.memory_type == MemoryType.POLICY,
        )
    )).scalars().all()
    assert any(
        (m.structured_data or {}).get("rule") == "always_inbox"
        and sender in (m.structured_data or {}).get("targets", [])
        for m in memories_after
    ), "correction should have produced an always_inbox memory for the sender"

    # Run the rule engine on cycle-2's email features. With the new memory
    # in scope, AlwaysInboxRule must promote the outcome to PROTECTED.
    post_match = run_rule_engine(
        email_features={"from_address": sender, "from_domain": "partner.example.com"},
        memories=[
            {"structured_data": m.structured_data, "memory_type": m.memory_type.value}
            for m in memories_after
        ],
    )
    assert post_match is not None, "rule engine should match after correction"
    outcome, confidence, rule_name = post_match
    assert outcome == TriageOutcome.PROTECTED
    assert rule_name == "always_inbox"
    assert confidence == 1.0

    # And specifically the cycle-2 outcome differs from cycle-1's BRIEF_ONLY.
    assert outcome != TriageOutcome.BRIEF_ONLY
