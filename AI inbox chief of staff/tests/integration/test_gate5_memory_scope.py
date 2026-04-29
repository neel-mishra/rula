"""Gate 5 — MemoryQueryAgent scope correctness.

Verifies that scope filtering on memory retrieval is honoured:

  - Mailbox-scoped memory → returned ONLY when querying with that mailbox_id;
    a query against a different mailbox returns an empty list.
  - User-global memory (applies_to_all_mailboxes=True) → returned across
    all of a user's mailboxes.
  - Fallback _text_search path is exercised because SQLite does not support
    pgvector and Memory.embedding stays NULL on insert. (This mirrors the
    pattern used in tests/integration/test_feedback_loop_e2e.py — direct
    DB read, with semantic search transparently falling back.)
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest


def _patched_get_db_session(session):
    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


async def _seed_two_mailboxes(db, user_id):
    """Returns (mailbox_a_id, mailbox_b_id), both belonging to user_id."""
    from core.models.mailbox import Mailbox

    a_id = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
    b_id = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
    db.add(Mailbox(
        id=a_id, user_id=user_id,
        gmail_email="a@example.com", gmail_user_id="google-sub-a",
        is_active=True, is_connected=True,
    ))
    db.add(Mailbox(
        id=b_id, user_id=user_id,
        gmail_email="b@example.com", gmail_user_id="google-sub-b",
        is_active=True, is_connected=True,
    ))
    await db.flush()
    return a_id, b_id


def _add_memory(
    db,
    *,
    user_id,
    mailbox_id,
    scope,
    applies_to_all_mailboxes,
    content,
    targets,
):
    from core.models.memory import Memory, MemoryType

    db.add(Memory(
        id=uuid.uuid4(),
        user_id=user_id,
        mailbox_id=mailbox_id,
        scope=scope,
        applies_to_all_mailboxes=applies_to_all_mailboxes,
        memory_type=MemoryType.POLICY,
        content=content,
        structured_data={"rule": "always_inbox", "targets": targets},
        source="test",
        confidence=0.9,
        is_active=True,
    ))


@pytest.mark.asyncio
async def test_mailbox_scoped_memory_only_returned_for_owning_mailbox(
    db_session, sample_user_id,
):
    from core.models.memory import MemoryScope
    from core.schemas.contracts import MemoryQueryTask
    from subagents.memory import MemoryQueryAgent

    a_id, b_id = await _seed_two_mailboxes(db_session, sample_user_id)

    _add_memory(
        db_session,
        user_id=sample_user_id,
        mailbox_id=a_id,
        scope=MemoryScope.MAILBOX_SPECIFIC,
        applies_to_all_mailboxes=False,
        content="Always inbox alice@a.example.com (mailbox A only)",
        targets=["alice@a.example.com"],
    )
    await db_session.flush()

    # Query mailbox A → must find it.
    task_a = MemoryQueryTask(
        user_id=sample_user_id,
        mailbox_id=a_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        query="alice",
        memory_types=["policy"],
        top_k=10,
    )
    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        res_a = await MemoryQueryAgent().run(task_a)
    assert res_a.ok is True
    assert res_a.payload.total_retrieved == 1
    assert res_a.payload.memories[0]["scope"] == "mailbox_specific"
    assert "alice@a.example.com" in res_a.payload.memories[0]["structured_data"]["targets"]

    # Query mailbox B (same user) → must NOT see mailbox-A-scoped memory.
    task_b = MemoryQueryTask(
        user_id=sample_user_id,
        mailbox_id=b_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        query="alice",
        memory_types=["policy"],
        top_k=10,
    )
    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        res_b = await MemoryQueryAgent().run(task_b)
    assert res_b.ok is True
    assert res_b.payload.total_retrieved == 0
    assert res_b.payload.memories == []


@pytest.mark.asyncio
async def test_user_global_memory_visible_across_all_mailboxes(
    db_session, sample_user_id,
):
    from core.models.memory import MemoryScope
    from core.schemas.contracts import MemoryQueryTask
    from subagents.memory import MemoryQueryAgent

    a_id, b_id = await _seed_two_mailboxes(db_session, sample_user_id)

    _add_memory(
        db_session,
        user_id=sample_user_id,
        mailbox_id=None,
        scope=MemoryScope.USER_GLOBAL,
        applies_to_all_mailboxes=True,
        content="Never archive legal.example.com (everywhere)",
        targets=["legal.example.com"],
    )
    await db_session.flush()

    for mb_id in (a_id, b_id):
        task = MemoryQueryTask(
            user_id=sample_user_id,
            mailbox_id=mb_id,
            correlation_id=str(uuid.uuid4()),
            policy_version="v1",
            query="legal",
            memory_types=["policy"],
            top_k=10,
        )
        with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
            res = await MemoryQueryAgent().run(task)
        assert res.ok is True, res
        assert res.payload.total_retrieved == 1, f"missing on mailbox {mb_id}"
        assert res.payload.memories[0]["scope"] == "user_global"


@pytest.mark.asyncio
async def test_user_global_without_applies_flag_is_not_returned(
    db_session, sample_user_id,
):
    """Defensive: a USER_GLOBAL row with applies_to_all_mailboxes=False
    must NOT leak into another mailbox's query — the scope filter requires
    BOTH USER_GLOBAL and applies_to_all_mailboxes=True."""
    from core.models.memory import MemoryScope
    from core.schemas.contracts import MemoryQueryTask
    from subagents.memory import MemoryQueryAgent

    a_id, b_id = await _seed_two_mailboxes(db_session, sample_user_id)

    _add_memory(
        db_session,
        user_id=sample_user_id,
        mailbox_id=None,
        scope=MemoryScope.USER_GLOBAL,
        applies_to_all_mailboxes=False,  # contradiction — should not be returned
        content="malformed user-global row",
        targets=["x@y.com"],
    )
    await db_session.flush()

    task = MemoryQueryTask(
        user_id=sample_user_id,
        mailbox_id=b_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        query="x",
        memory_types=["policy"],
        top_k=10,
    )
    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        res = await MemoryQueryAgent().run(task)
    assert res.ok is True
    assert res.payload.total_retrieved == 0


@pytest.mark.asyncio
async def test_other_users_memories_never_leak(
    db_session, sample_user_id,
):
    """user_id filter must hold even with shared mailbox UUIDs."""
    from core.models.memory import MemoryScope
    from core.models.user import User
    from core.schemas.contracts import MemoryQueryTask
    from subagents.memory import MemoryQueryAgent

    a_id, _b_id = await _seed_two_mailboxes(db_session, sample_user_id)

    other_user_id = uuid.UUID("00000000-0000-0000-0000-0000000000ff")
    db_session.add(User(
        id=other_user_id,
        email="other@example.com",
        display_name="Other",
        is_active=True,
    ))
    await db_session.flush()

    _add_memory(
        db_session,
        user_id=other_user_id,
        mailbox_id=None,
        scope=MemoryScope.USER_GLOBAL,
        applies_to_all_mailboxes=True,
        content="other-user secret rule",
        targets=["secret@other.com"],
    )
    await db_session.flush()

    task = MemoryQueryTask(
        user_id=sample_user_id,
        mailbox_id=a_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        query="secret",
        memory_types=["policy"],
        top_k=10,
    )
    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        res = await MemoryQueryAgent().run(task)
    assert res.ok is True
    assert res.payload.total_retrieved == 0
