"""Gate 5 — PolicyAgent instruction parsing correctness.

Covers:
  - Clear instruction → rule extracted, persisted as MAILBOX_SPECIFIC Memory.
  - Ambiguous instruction → clarifying question returned, no rule persisted.
  - Multi-turn: clarification answered → rule extracted on the second turn.
  - scope='user_global' / applies_to_all_mailboxes=True routes to USER_GLOBAL.

Mocks:
  - core.llm.client.get_llm_client → fake async client returning canned JSON
    (one payload per call so we can drive _analyze_instruction then
    _extract_rules deterministically).
  - subagents.policy.get_db_session (imported inside _execute) → wrapped to
    yield the test db_session so writes land in the same in-memory SQLite.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import select


# ────────────────────────────── helpers ──────────────────────────────────


def _patched_get_db_session(session):
    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


class _FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _ScriptedLLMClient:
    """Returns canned JSON payloads in order, one per .complete() call."""

    def __init__(self, payloads: list[dict | list]) -> None:
        self._payloads = [json.dumps(p) for p in payloads]
        self._idx = 0

    async def complete(self, *args, **kwargs) -> _FakeLLMResponse:
        if self._idx >= len(self._payloads):
            raise AssertionError(
                f"LLM called more times ({self._idx + 1}) than scripted ({len(self._payloads)})"
            )
        out = self._payloads[self._idx]
        self._idx += 1
        return _FakeLLMResponse(content=out)


async def _seed_mailbox(db, user_id, mailbox_id):
    from core.models.mailbox import Mailbox

    db.add(Mailbox(
        id=mailbox_id,
        user_id=user_id,
        gmail_email="user@example.com",
        gmail_user_id="google-sub-test",
        is_active=True,
        is_connected=True,
    ))
    await db.flush()


# ────────────────────────────── tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_clear_instruction_extracts_mailbox_specific_rule(
    db_session, sample_user_id, sample_mailbox_id,
):
    """A specific instruction → PolicyAgent persists exactly one POLICY memory
    with the parsed rule_type/targets and MAILBOX_SPECIFIC scope."""
    from core.models.memory import Memory, MemoryScope, MemoryType
    from core.schemas.contracts import PolicyCompileTask
    from subagents.policy import PolicyAgent

    await _seed_mailbox(db_session, sample_user_id, sample_mailbox_id)

    fake_llm = _ScriptedLLMClient([
        # _analyze_instruction
        {"needs_clarification": False, "clarification_question": None, "ambiguity_reason": None},
        # _extract_rules
        [{
            "rule_type": "always_inbox",
            "targets": ["boss@example.com"],
            "content": "Always keep emails from boss@example.com in inbox",
            "scope": "mailbox_specific",
            "applies_to_all_mailboxes": False,
            "confidence": 0.95,
        }],
    ])

    task = PolicyCompileTask(
        user_id=sample_user_id,
        mailbox_id=sample_mailbox_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        instruction_text="Always inbox emails from boss@example.com",
        source="assistant",
    )

    with patch("core.llm.client.get_llm_client", return_value=fake_llm):
        with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
            agent = PolicyAgent()
            response = await agent.run(task)

    assert response.ok is True
    payload = response.payload
    assert payload.rules_created == 1
    assert payload.needs_clarification is False
    assert payload.clarification_question is None

    rows = (await db_session.execute(
        select(Memory).where(
            Memory.user_id == sample_user_id,
            Memory.memory_type == MemoryType.POLICY,
        )
    )).scalars().all()
    assert len(rows) == 1
    mem = rows[0]
    assert mem.scope == MemoryScope.MAILBOX_SPECIFIC
    assert mem.mailbox_id == sample_mailbox_id
    assert mem.applies_to_all_mailboxes is False
    assert mem.structured_data["rule"] == "always_inbox"
    assert "boss@example.com" in mem.structured_data["targets"]
    assert mem.source == "assistant"
    assert mem.is_active is True
    assert mem.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_ambiguous_instruction_returns_clarifying_question(
    db_session, sample_user_id, sample_mailbox_id,
):
    """An ambiguous instruction must NOT persist a memory and must surface a
    clarifying question on the result envelope."""
    from core.models.memory import Memory
    from core.schemas.contracts import PolicyCompileTask
    from subagents.policy import PolicyAgent

    await _seed_mailbox(db_session, sample_user_id, sample_mailbox_id)

    fake_llm = _ScriptedLLMClient([
        # _analyze_instruction → ambiguous
        {
            "needs_clarification": True,
            "clarification_question": "Which sender should I treat differently?",
            "ambiguity_reason": "no specific sender, domain, or category mentioned",
        },
        # _extract_rules must NOT be called when ambiguous; if it is, scripted
        # client raises AssertionError.
    ])

    task = PolicyCompileTask(
        user_id=sample_user_id,
        mailbox_id=sample_mailbox_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        instruction_text="handle these better",
        source="assistant",
    )

    with patch("core.llm.client.get_llm_client", return_value=fake_llm):
        with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
            response = await PolicyAgent().run(task)

    assert response.ok is True
    payload = response.payload
    assert payload.rules_created == 0
    assert payload.needs_clarification is True
    assert payload.clarification_question == "Which sender should I treat differently?"

    # No memory created.
    rows = (await db_session.execute(
        select(Memory).where(Memory.user_id == sample_user_id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_clarification_then_rule_extracted_multiturn(
    db_session, sample_user_id, sample_mailbox_id,
):
    """Turn 1 ambiguous → clarification. Turn 2 (clarified instruction) →
    rule extracted and persisted."""
    from core.models.memory import Memory, MemoryScope
    from core.schemas.contracts import PolicyCompileTask
    from subagents.policy import PolicyAgent

    await _seed_mailbox(db_session, sample_user_id, sample_mailbox_id)

    # ── Turn 1: ambiguous ────────────────────────────────────────────────
    llm_turn1 = _ScriptedLLMClient([
        {"needs_clarification": True,
         "clarification_question": "Who specifically?",
         "ambiguity_reason": "no sender given"},
    ])

    task1 = PolicyCompileTask(
        user_id=sample_user_id,
        mailbox_id=sample_mailbox_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        instruction_text="be smarter about routing",
        source="assistant",
    )

    with patch("core.llm.client.get_llm_client", return_value=llm_turn1):
        with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
            r1 = await PolicyAgent().run(task1)
    assert r1.payload.needs_clarification is True
    assert r1.payload.rules_created == 0

    # ── Turn 2: user has answered the clarification ─────────────────────
    llm_turn2 = _ScriptedLLMClient([
        {"needs_clarification": False, "clarification_question": None, "ambiguity_reason": None},
        [{
            "rule_type": "always_brief",
            "targets": ["newsletters@news.example.com"],
            "content": "Always brief newsletters from newsletters@news.example.com",
            "scope": "mailbox_specific",
            "applies_to_all_mailboxes": False,
            "confidence": 0.9,
        }],
    ])

    task2 = PolicyCompileTask(
        user_id=sample_user_id,
        mailbox_id=sample_mailbox_id,
        correlation_id=task1.correlation_id,  # same convo trace
        policy_version="v1",
        instruction_text="brief newsletters from newsletters@news.example.com instead of inboxing",
        source="assistant",
    )

    with patch("core.llm.client.get_llm_client", return_value=llm_turn2):
        with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
            r2 = await PolicyAgent().run(task2)

    assert r2.payload.needs_clarification is False
    assert r2.payload.rules_created == 1

    rows = (await db_session.execute(
        select(Memory).where(Memory.user_id == sample_user_id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].scope == MemoryScope.MAILBOX_SPECIFIC
    assert rows[0].structured_data["rule"] == "always_brief"
    assert "newsletters@news.example.com" in rows[0].structured_data["targets"]


@pytest.mark.asyncio
async def test_user_global_scope_routes_to_user_global_with_null_mailbox(
    db_session, sample_user_id, sample_mailbox_id,
):
    """When the LLM returns scope='user_global', the persisted memory must
    have scope=USER_GLOBAL and mailbox_id=NULL, even though the task carried
    a specific mailbox_id."""
    from core.models.memory import Memory, MemoryScope
    from core.schemas.contracts import PolicyCompileTask
    from subagents.policy import PolicyAgent

    await _seed_mailbox(db_session, sample_user_id, sample_mailbox_id)

    fake_llm = _ScriptedLLMClient([
        {"needs_clarification": False, "clarification_question": None, "ambiguity_reason": None},
        [{
            "rule_type": "never_archive",
            "targets": ["legal.example.com"],
            "content": "Never archive legal.example.com on any mailbox",
            "scope": "user_global",
            "applies_to_all_mailboxes": True,
            "confidence": 0.9,
        }],
    ])

    task = PolicyCompileTask(
        user_id=sample_user_id,
        mailbox_id=sample_mailbox_id,
        correlation_id=str(uuid.uuid4()),
        policy_version="v1",
        instruction_text="On all mailboxes, never archive anything from legal.example.com",
        source="assistant",
    )

    with patch("core.llm.client.get_llm_client", return_value=fake_llm):
        with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
            response = await PolicyAgent().run(task)

    assert response.ok is True
    assert response.payload.rules_created == 1

    rows = (await db_session.execute(
        select(Memory).where(Memory.user_id == sample_user_id)
    )).scalars().all()
    assert len(rows) == 1
    mem = rows[0]
    assert mem.scope == MemoryScope.USER_GLOBAL
    assert mem.mailbox_id is None
    assert mem.applies_to_all_mailboxes is True
    assert mem.structured_data["rule"] == "never_archive"
