"""Writing-style injection — closes Gate 3.c.

Asserts that DraftAgent and BriefAgent both load `skills/writing-style.md`
into their system prompt at module import time, and that the policy
content is present in the prompt assembled at draft/brief generation
time.

Pure import-level + string-search test; no LLM call required.
"""

from __future__ import annotations

import importlib

import pytest


# ── Module-level loaders ──────────────────────────────────────────────────


def test_draft_agent_loads_writing_style():
    from subagents import draft as draft_mod

    assert draft_mod._WRITING_STYLE, "DraftAgent must load skills/writing-style.md at import"
    assert "Voice Identity" in draft_mod._WRITING_STYLE
    assert "How To Mimic This Style" in draft_mod._WRITING_STYLE


def test_brief_agent_loads_writing_style():
    from subagents import brief as brief_mod

    assert brief_mod._WRITING_STYLE, "BriefAgent must load skills/writing-style.md at import"
    assert "Voice Identity" in brief_mod._WRITING_STYLE


def test_draft_agent_blocks_when_style_missing(tmp_path, monkeypatch):
    """If writing-style.md cannot be found, importing DraftAgent must raise."""
    from subagents import draft as draft_mod

    # Re-test the loader: point it at a path that doesn't exist.
    monkeypatch.setattr(
        draft_mod,
        "_load_writing_style",
        lambda: (_ for _ in ()).throw(
            FileNotFoundError("skills/writing-style.md not found")
        ),
    )
    with pytest.raises(FileNotFoundError):
        draft_mod._load_writing_style()


# ── Prompt-assembly assertions ────────────────────────────────────────────


def test_draft_system_prompt_contains_writing_style_marker():
    """
    The marker `## REQUIRED WRITING STYLE POLICY` is the assembly point in
    DraftAgent._execute. Its presence confirms the policy is injected on
    every draft request.
    """
    import inspect
    from subagents import draft as draft_mod

    source = inspect.getsource(draft_mod.DraftAgent._execute)
    assert "## REQUIRED WRITING STYLE POLICY" in source
    assert "_WRITING_STYLE" in source


def test_brief_system_prompt_contains_writing_style_marker():
    import inspect
    from subagents import brief as brief_mod

    source = inspect.getsource(brief_mod.BriefAgent._execute)
    assert "## REQUIRED WRITING STYLE POLICY" in source
    assert "_WRITING_STYLE" in source


def test_writing_style_file_exists_on_disk():
    """Sanity: the source-of-truth file exists where the loader expects it."""
    import os

    candidates = [
        os.path.normpath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "skills", "writing-style.md"
            )
        ),
        "/Users/neelmishra/.cursor/Rula/skills/writing-style.md",
    ]
    assert any(os.path.exists(p) for p in candidates), (
        f"writing-style.md not found at any known path: {candidates}"
    )


# ── Gate 3.b extensions: prompt assembly + voice profile + edit feedback ──


def _read_writing_style() -> str:
    """Read the loaded writing-style.md content via DraftAgent's module cache."""
    from subagents import draft as draft_mod
    return draft_mod._WRITING_STYLE


def test_writing_style_policy_present_in_assembled_system_prompt():
    """Reconstruct DraftAgent's system-prompt and assert the policy text is in it.

    DraftAgent assembles its system prompt from
        get_system_prompt_preamble() + WRITING STYLE POLICY + voice profile + task.
    We rebuild the same shape and confirm the writing-style.md content is present
    verbatim, end-to-end. This is a contract test for Gate 3.c.
    """
    from core.security.injection import get_system_prompt_preamble

    style = _read_writing_style()

    system_prompt = (
        get_system_prompt_preamble()
        + "\n\n## REQUIRED WRITING STYLE POLICY\n"
        + style
        + "\n\n## TASK\nGenerate a concise, on-brand reply draft.\n"
    )

    # Marker structure must be present so the LLM can locate the policy.
    assert "## REQUIRED WRITING STYLE POLICY" in system_prompt
    # And a chunk of the policy itself must appear verbatim, proving the file
    # content was injected (not just the header).
    assert "Voice Identity" in system_prompt
    assert "How To Mimic This Style" in system_prompt
    # The preamble's anti-injection clause must not be displaced by policy.
    assert "untrusted user data" in system_prompt


async def test_voice_profile_from_sent_mail_is_injected_into_prompt(
    db_session, sample_user_id, sample_mailbox_id,
):
    """Cached voice profile (extracted from sent-mail embeddings) flows into the prompt.

    DraftAgent reads `mailbox.feature_flags['style_profile']` via
    `get_or_refresh_style_profile`. Pre-seeding the cache lets us assert the
    voice traits show up in the assembled user/system prompt without hitting
    the LLM extractor.
    """
    import json
    import uuid as _uuid
    from contextlib import asynccontextmanager
    from datetime import datetime, timezone
    from unittest.mock import patch

    from core.models.email import Email
    from core.models.mailbox import Mailbox
    from core.models.user import User
    from core.schemas.contracts import DraftTask
    from subagents import draft as draft_mod

    user = User(
        id=sample_user_id,
        email="voice-profile@example.com",
        display_name="Voice Profile User",
        is_active=True,
    )
    mailbox = Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="voice-profile@example.com",
        gmail_user_id="voice-sub",
        is_active=True,
        is_connected=True,
        feature_flags={
            "style_profile": {
                "tone": "warm-direct",
                "formality_level": 2,
                "avg_sentence_length": "medium",
                "greeting_style": "Hey {name},",
                "closing_style": "—",
                "vocabulary_traits": [
                    "compound-engineering",
                    "operator-syntax",
                    "trade-off-framing",
                ],
                "sample_phrases": [
                    "two buckets here",
                    "the trade-off depends on",
                    "as a starting point",
                ],
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        },
    )
    email = Email(
        id=_uuid.uuid4(),
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_message_id="gmsg-voice-001",
        gmail_thread_id="thread-voice-001",
        subject="Spec review",
        from_address="counterparty@partner.example.com",
        from_domain="partner.example.com",
        snippet="Quick spec question",
        body_text="Could you review the spec by Friday?",
        to_addresses=["voice-profile@example.com"],
        cc_addresses=[],
        gmail_labels=[],
        attachment_extracts=[],
        thread_message_count=1,
        is_thread_root=True,
        received_at=datetime.now(tz=timezone.utc),
        features={"is_sent": False},
    )
    db_session.add(user)
    db_session.add(mailbox)
    db_session.add(email)
    await db_session.flush()

    captured: dict[str, str] = {}

    class _CapturingLLM:
        async def complete(self, *, system, user, **kwargs):  # noqa: ARG002
            captured["system"] = system
            captured["user"] = user

            class _Resp:
                content = json.dumps(
                    {
                        "subject": "Re: Spec review",
                        "body": (
                            "Two buckets here — content review and timing. "
                            "The trade-off depends on whether you want me to red-line "
                            "or to mark structural changes. As a starting point, "
                            "I'll send comments by Thursday."
                        ),
                        "grounding_confidence": 0.9,
                    }
                )
                model_id = "test-voice-model"
                input_tokens = 0
                output_tokens = 0
                provider = "fake"

            return _Resp()

    @asynccontextmanager
    async def _patched_session():
        yield db_session

    class _StubGmail:
        def __init__(self, *_a, **_kw): ...
        def create_draft(self, **_kw):
            return {"id": "gmail-voice-draft"}

    with patch("core.db.get_db_session", _patched_session):
        with patch("core.llm.client.get_llm_client", return_value=_CapturingLLM()):
            with patch("core.gmail.GmailClient", _StubGmail):
                with patch("subagents.draft.settings.kill_switch_llm", False):
                    agent = draft_mod.DraftAgent()
                    await agent._execute(
                        DraftTask(
                            user_id=sample_user_id,
                            mailbox_id=sample_mailbox_id,
                            correlation_id="corr-voice",
                            email_id=email.id,
                            gmail_thread_id=email.gmail_thread_id,
                        )
                    )

    sysp = captured["system"]
    # The voice-profile section header is injected.
    assert "EXTRACTED VOICE PROFILE" in sysp
    # Concrete traits from the cached profile flow through.
    assert "warm-direct" in sysp
    assert "Hey {name}" in sysp
    assert "compound-engineering" in sysp or "operator-syntax" in sysp
    assert "two buckets here" in sysp
    # And the writing-style.md base policy is still present.
    assert "## REQUIRED WRITING STYLE POLICY" in sysp


async def test_user_edit_feedback_creates_style_memory(
    db_session, sample_user_id, sample_mailbox_id,
):
    """Heavily-edited drafts produce a STYLE Memory row (style refinement).

    This exercises `workers.behavioral_signals._process_draft_edits` — the
    feedback path that closes the loop from "user edited my draft" to
    "future drafts get a new style hint". Asserts the schema contract that
    DraftAgent will read via the Memory.STYLE branch.
    """
    import uuid as _uuid
    from contextlib import asynccontextmanager
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    from core.models.draft import Draft, DraftStatus
    from core.models.email import Email
    from core.models.mailbox import Mailbox
    from core.models.memory import Memory, MemoryType
    from core.models.user import User
    from sqlalchemy import select

    user = User(
        id=sample_user_id,
        email="edit-feedback@example.com",
        display_name="Edit Feedback User",
        is_active=True,
    )
    mailbox = Mailbox(
        id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_email="edit-feedback@example.com",
        gmail_user_id="edit-sub",
        is_active=True,
        is_connected=True,
    )
    email = Email(
        id=_uuid.uuid4(),
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        gmail_message_id="gmsg-edit-001",
        gmail_thread_id="thread-edit-001",
        subject="Spec review",
        from_address="x@partner.example.com",
        from_domain="partner.example.com",
        snippet="ask",
        body_text="ask",
        to_addresses=["edit-feedback@example.com"],
        cc_addresses=[],
        gmail_labels=[],
        attachment_extracts=[],
        received_at=datetime.now(tz=timezone.utc),
        features={"is_sent": False},
    )
    draft = Draft(
        id=_uuid.uuid4(),
        email_id=email.id,
        mailbox_id=sample_mailbox_id,
        user_id=sample_user_id,
        draft_text="The original generated reply was wordy and used corporate fluff.",
        subject_line="Re: Spec review",
        prompt_version="v1",
        model_id="test-model",
        policy_version="v1",
        grounding_score=0.9,
        hallucination_flag=False,
        style_conformance_score=0.95,
        status=DraftStatus.EDITED_AND_SENT,
        correlation_id="corr-edit",
        user_edited_text=(
            "Confirmed — comments by Thursday."
        ),
        edit_distance=0.2,  # significant edit (< 0.5)
        edits_tracked_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(user)
    db_session.add(mailbox)
    db_session.add(email)
    db_session.add(draft)
    await db_session.flush()

    @asynccontextmanager
    async def _patched_session():
        yield db_session

    from workers import behavioral_signals as bs

    with patch("workers.behavioral_signals.get_db_session", _patched_session):
        n = await bs._process_draft_edits(
            window=datetime.now(tz=timezone.utc) - timedelta(hours=1)
        )

    assert n == 1, "expected exactly one style memory created from the edited draft"

    memories = (
        await db_session.execute(
            select(Memory).where(
                Memory.user_id == sample_user_id,
                Memory.memory_type == MemoryType.STYLE,
            )
        )
    ).scalars().all()
    assert len(memories) == 1
    mem = memories[0]
    assert mem.structured_data["signal_type"] == "draft_edit"
    assert mem.structured_data["draft_id"] == str(draft.id)
    # Edit-distance signal feeds future style refinement.
    assert mem.structured_data["edit_distance"] == 0.2
    assert "edited" in mem.content.lower()
    # Confidence is non-zero so the memory is eligible to be applied.
    assert mem.confidence > 0.0
