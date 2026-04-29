"""Gate 3 — DraftAgent end-to-end grounding tests.

Covers the three behaviours called out in the roadmap for Gate 3
"Draft generation integration with grounding checks":

  1. Drafts whose grounding_score crosses the launch threshold
     persist as DraftStatus.GENERATED; drafts below the auto-reject
     floor (< 0.4) persist as DraftStatus.REJECTED with
     hallucination_flag=True.
  2. Hallucination flag fires when the LLM returns a low
     grounding_confidence (< 0.6) — even if the draft is still
     stored.
  3. Multi-turn thread context: prior thread emails are loaded into
     the user-message that DraftAgent sends to the LLM.

The DraftAgent's LLM and Gmail clients are patched at the test-
function level so this exercises the agent's real pipeline
(prompt assembly, sanitisation, DB persistence, status logic)
deterministically without external services.
"""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from core.models.draft import Draft, DraftStatus
from core.models.email import Email
from core.models.mailbox import Mailbox
from core.models.user import User
from core.schemas.contracts import DraftTask


# ── helpers ───────────────────────────────────────────────────────────────


def _patched_get_db_session(session):
    @asynccontextmanager
    async def _cm():
        yield session

    return _cm


class _FakeLLMResponse:
    def __init__(self, content: str, model_id: str = "test-model-v1") -> None:
        self.content = content
        self.model_id = model_id
        self.input_tokens = 0
        self.output_tokens = 0
        self.provider = "fake"


class _FakeLLMClient:
    """Records the prompts it received so the test can assert on context."""

    def __init__(self, payload: dict, model_id: str = "test-model-v1") -> None:
        self._payload = payload
        self._model_id = model_id
        self.calls: list[dict] = []

    async def complete(self, *args, **kwargs):  # noqa: ARG002
        self.calls.append(kwargs)
        return _FakeLLMResponse(json.dumps(self._payload), model_id=self._model_id)


class _FakeGmailClient:
    """Returns a Gmail draft id without making any HTTP calls."""

    instances: list["_FakeGmailClient"] = []

    def __init__(self, mailbox) -> None:  # noqa: ARG002
        _FakeGmailClient.instances.append(self)

    def create_draft(self, **kwargs):  # noqa: ARG002
        return {"id": "gmail-draft-fake-001"}


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_user(sample_user_id) -> User:
    return User(
        id=sample_user_id,
        email="operator@example.com",
        display_name="Test Operator",
        is_active=True,
    )


@pytest.fixture
def sample_mailbox(sample_user_id, sample_mailbox_id) -> Mailbox:
    # Pre-cache a style profile so DraftAgent doesn't try to extract one
    # via an LLM call we haven't mocked here.
    return Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="operator@example.com",
        gmail_user_id="google-sub-test",
        is_active=True,
        is_connected=True,
        feature_flags={
            "style_profile": {
                "tone": "direct",
                "formality_level": 3,
                "avg_sentence_length": "medium",
                "greeting_style": "Hi {name},",
                "closing_style": "—",
                "vocabulary_traits": ["concise", "operator"],
                "sample_phrases": ["happy to dig in", "two buckets"],
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        },
    )


async def _seed_email(
    db_session,
    *,
    mailbox: Mailbox,
    user: User,
    subject: str = "Quick spec question",
    body_text: str = (
        "Could you review the attached pricing spec and let me know what you think "
        "about the API tier breakdown? I'd like to lock the term sheet by Friday."
    ),
    gmail_thread_id: str = "thread-grounding-001",
    gmail_message_id: str | None = None,
    received_at: datetime | None = None,
) -> Email:
    email = Email(
        id=uuid.uuid4(),
        mailbox_id=mailbox.id,
        user_id=user.id,
        gmail_message_id=gmail_message_id or f"gmsg-{uuid.uuid4().hex[:8]}",
        gmail_thread_id=gmail_thread_id,
        subject=subject,
        from_address="counterparty@partner.example.com",
        from_domain="partner.example.com",
        snippet=body_text[:120],
        body_text=body_text,
        to_addresses=["operator@example.com"],
        cc_addresses=[],
        gmail_labels=[],
        attachment_extracts=[],
        thread_message_count=1,
        is_thread_root=True,
        received_at=received_at or datetime.now(tz=timezone.utc),
        features={"is_sent": False, "is_reply": False},
    )
    db_session.add(email)
    await db_session.flush()
    return email


# ── Tests ─────────────────────────────────────────────────────────────────


async def test_draft_with_high_grounding_persists_as_generated(
    db_session, sample_user, sample_mailbox
):
    """grounding_score >= threshold → status GENERATED, hallucination_flag False."""
    from subagents import draft as draft_mod

    db_session.add(sample_user)
    db_session.add(sample_mailbox)
    await db_session.flush()

    email = await _seed_email(db_session, mailbox=sample_mailbox, user=sample_user)

    fake_llm = _FakeLLMClient(
        payload={
            "subject": "Re: Quick spec question",
            "body": (
                "Thanks for the spec — I'd frame the pricing review as two buckets: "
                "API tier breakdown and term-sheet timing. The trade-off depends on "
                "whether we lock pricing first or align on volume tiers. I'll send "
                "comments before Friday."
            ),
            "grounding_confidence": 0.92,
        }
    )

    _FakeGmailClient.instances = []

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("core.llm.client.get_llm_client", return_value=fake_llm):
            with patch("core.gmail.GmailClient", _FakeGmailClient):
                with patch("subagents.draft.settings.kill_switch_llm", False):
                    agent = draft_mod.DraftAgent()
                    result = await agent._execute(
                        DraftTask(
                            user_id=sample_user.id,
                            mailbox_id=sample_mailbox.id,
                            correlation_id="corr-grounding-pass",
                            email_id=email.id,
                            gmail_thread_id=email.gmail_thread_id,
                        )
                    )

    assert result.grounding_score >= 0.6
    assert result.hallucination_flag is False
    assert result.draft_text  # body present
    assert result.gmail_draft_id == "gmail-draft-fake-001"
    assert len(_FakeGmailClient.instances) == 1

    # Persistence: status GENERATED, scores stored.
    persisted = (
        await db_session.execute(select(Draft).where(Draft.id == result.draft_id))
    ).scalar_one()
    assert persisted.status == DraftStatus.GENERATED
    assert persisted.grounding_score == pytest.approx(0.92)
    assert persisted.hallucination_flag is False
    assert persisted.style_conformance_score is not None


async def test_draft_below_grounding_floor_is_auto_rejected(
    db_session, sample_user, sample_mailbox
):
    """grounding_score < 0.4 → DraftStatus.REJECTED, never written to Gmail."""
    from subagents import draft as draft_mod

    db_session.add(sample_user)
    db_session.add(sample_mailbox)
    await db_session.flush()

    email = await _seed_email(db_session, mailbox=sample_mailbox, user=sample_user)

    fake_llm = _FakeLLMClient(
        payload={
            "subject": "Re: Quick spec question",
            "body": "Sounds good, will follow up later.",
            "grounding_confidence": 0.2,  # below the 0.4 reject floor
        }
    )

    _FakeGmailClient.instances = []

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("core.llm.client.get_llm_client", return_value=fake_llm):
            with patch("core.gmail.GmailClient", _FakeGmailClient):
                with patch("subagents.draft.settings.kill_switch_llm", False):
                    agent = draft_mod.DraftAgent()
                    result = await agent._execute(
                        DraftTask(
                            user_id=sample_user.id,
                            mailbox_id=sample_mailbox.id,
                            correlation_id="corr-grounding-reject",
                            email_id=email.id,
                            gmail_thread_id=email.gmail_thread_id,
                        )
                    )

    # The DraftAgent must never call Gmail when rejecting.
    assert _FakeGmailClient.instances == []
    assert result.gmail_draft_id is None
    assert result.hallucination_flag is True
    assert result.grounding_score < 0.4

    persisted = (
        await db_session.execute(select(Draft).where(Draft.id == result.draft_id))
    ).scalar_one()
    assert persisted.status == DraftStatus.REJECTED
    assert persisted.hallucination_flag is True
    assert persisted.gmail_draft_id is None


async def test_low_grounding_confidence_flags_hallucination(
    db_session, sample_user, sample_mailbox
):
    """Email lacking factual hooks → low grounding_confidence → flagged."""
    from subagents import draft as draft_mod

    db_session.add(sample_user)
    db_session.add(sample_mailbox)
    await db_session.flush()

    # Empty-ish email — no concrete dates, names, or asks.
    email = await _seed_email(
        db_session,
        mailbox=sample_mailbox,
        user=sample_user,
        subject="hi",
        body_text="hi",
        gmail_thread_id="thread-no-hooks",
    )

    # Between the auto-reject floor (0.4) and the hallucination threshold
    # (0.6): the draft persists but the flag must fire.
    fake_llm = _FakeLLMClient(
        payload={
            "subject": "Re: hi",
            "body": "Happy to help — what context do you need?",
            "grounding_confidence": 0.45,
        }
    )

    _FakeGmailClient.instances = []

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("core.llm.client.get_llm_client", return_value=fake_llm):
            with patch("core.gmail.GmailClient", _FakeGmailClient):
                with patch("subagents.draft.settings.kill_switch_llm", False):
                    agent = draft_mod.DraftAgent()
                    result = await agent._execute(
                        DraftTask(
                            user_id=sample_user.id,
                            mailbox_id=sample_mailbox.id,
                            correlation_id="corr-no-hooks",
                            email_id=email.id,
                            gmail_thread_id=email.gmail_thread_id,
                        )
                    )

    assert 0.4 <= result.grounding_score < 0.6
    assert result.hallucination_flag is True

    persisted = (
        await db_session.execute(select(Draft).where(Draft.id == result.draft_id))
    ).scalar_one()
    # Still GENERATED (above the 0.4 floor) but explicitly flagged.
    assert persisted.status == DraftStatus.GENERATED
    assert persisted.hallucination_flag is True


async def test_multi_turn_thread_context_is_passed_to_llm(
    db_session, sample_user, sample_mailbox
):
    """5 prior thread messages must be loaded and surfaced to the LLM."""
    from subagents import draft as draft_mod

    db_session.add(sample_user)
    db_session.add(sample_mailbox)
    await db_session.flush()

    thread_id = "thread-multi-turn"
    base_time = datetime.now(tz=timezone.utc) - timedelta(days=2)

    # Five prior thread messages — each with a unique factual hook.
    prior_hooks = [
        "We agreed to revisit pricing in the API tier",
        "Eng lead confirmed the migration window is Tuesday",
        "Procurement requires a redlined term sheet by Friday",
        "Security flagged the cert rotation as a blocker",
        "Onboarding spec needs an owner from your side",
    ]
    for i, hook in enumerate(prior_hooks):
        await _seed_email(
            db_session,
            mailbox=sample_mailbox,
            user=sample_user,
            subject=f"Re: Q3 partnership — message {i}",
            body_text=hook,
            gmail_thread_id=thread_id,
            gmail_message_id=f"gmsg-thread-{i}",
            received_at=base_time + timedelta(hours=i),
        )

    # The current email being replied to.
    current = await _seed_email(
        db_session,
        mailbox=sample_mailbox,
        user=sample_user,
        subject="Re: Q3 partnership — final ask",
        body_text="Pulling all of this together: can you confirm the term sheet, migration window, and onboarding owner in one note?",
        gmail_thread_id=thread_id,
        gmail_message_id="gmsg-thread-current",
        received_at=base_time + timedelta(hours=10),
    )

    fake_llm = _FakeLLMClient(
        payload={
            "subject": "Re: Q3 partnership — final ask",
            "body": (
                "Thanks for tying these threads together — term sheet by Friday, "
                "migration window Tuesday, and we'll name the onboarding owner today. "
                "The trade-off depends on whether procurement signs before security "
                "closes the cert rotation."
            ),
            "grounding_confidence": 0.85,
        }
    )

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("core.llm.client.get_llm_client", return_value=fake_llm):
            with patch("core.gmail.GmailClient", _FakeGmailClient):
                with patch("subagents.draft.settings.kill_switch_llm", False):
                    agent = draft_mod.DraftAgent()
                    await agent._execute(
                        DraftTask(
                            user_id=sample_user.id,
                            mailbox_id=sample_mailbox.id,
                            correlation_id="corr-multi-turn",
                            email_id=current.id,
                            gmail_thread_id=thread_id,
                        )
                    )

    # Exactly one LLM call; its user message must contain thread history.
    assert len(fake_llm.calls) == 1
    user_msg = fake_llm.calls[0]["user"]
    assert "Thread history" in user_msg, user_msg[:300]
    # Each prior hook makes it into the prompt.
    for hook in prior_hooks:
        assert hook in user_msg, f"missing hook: {hook}"
    # The current email body is also there.
    assert "Pulling all of this together" in user_msg


async def test_thread_context_capped_at_five_messages(
    db_session, sample_user, sample_mailbox
):
    """DraftAgent's limit(5) must hold even when 8 prior messages exist."""
    from subagents import draft as draft_mod

    db_session.add(sample_user)
    db_session.add(sample_mailbox)
    await db_session.flush()

    thread_id = "thread-cap-test"
    base_time = datetime.now(tz=timezone.utc) - timedelta(days=3)

    # Seed 8 prior messages.
    hooks: list[str] = []
    for i in range(8):
        hook = f"prior-hook-marker-{i:02d}"
        hooks.append(hook)
        await _seed_email(
            db_session,
            mailbox=sample_mailbox,
            user=sample_user,
            subject=f"Re: thread cap — {i}",
            body_text=hook,
            gmail_thread_id=thread_id,
            gmail_message_id=f"gmsg-cap-{i}",
            received_at=base_time + timedelta(hours=i),
        )

    current = await _seed_email(
        db_session,
        mailbox=sample_mailbox,
        user=sample_user,
        subject="Re: thread cap — final",
        body_text="Final follow-up — please confirm.",
        gmail_thread_id=thread_id,
        gmail_message_id="gmsg-cap-final",
        received_at=base_time + timedelta(hours=20),
    )

    fake_llm = _FakeLLMClient(
        payload={
            "subject": "Re: thread cap — final",
            "body": "Confirmed — I'll respond by end of week with the redlined version.",
            "grounding_confidence": 0.7,
        }
    )

    with patch("core.db.get_db_session", _patched_get_db_session(db_session)):
        with patch("core.llm.client.get_llm_client", return_value=fake_llm):
            with patch("core.gmail.GmailClient", _FakeGmailClient):
                with patch("subagents.draft.settings.kill_switch_llm", False):
                    agent = draft_mod.DraftAgent()
                    await agent._execute(
                        DraftTask(
                            user_id=sample_user.id,
                            mailbox_id=sample_mailbox.id,
                            correlation_id="corr-cap",
                            email_id=current.id,
                            gmail_thread_id=thread_id,
                        )
                    )

    user_msg = fake_llm.calls[0]["user"]
    present = [h for h in hooks if h in user_msg]
    # DraftAgent's `.limit(5)` keeps thread context bounded.
    assert len(present) == 5, f"expected 5 prior messages in prompt, got {len(present)}"
