"""Integration tests for the full ingestion + triage + draft pipeline.

Rules:
- Real Postgres (test DB on :5433) — no SQLAlchemy mocks.
- GmailClient and Anthropic LLM calls are mocked.
- Each test uses the `async_session` fixture which rolls back after the test.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_gmail_message(gmail_message_id: str) -> dict:
    """Return a minimal Gmail API message dict that normalizer.normalize_message can parse."""
    import base64

    body_text = "We need the updated numbers before the board call at 5pm. Action required."
    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()

    return {
        "id": gmail_message_id,
        "threadId": f"thread_{gmail_message_id}",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Jane CFO <cfo@example.com>"},
                {"name": "Subject", "value": "Urgent: Q2 budget review by EOD"},
                {"name": "Date", "value": "Wed, 30 Apr 2026 09:00:00 +0000"},
            ],
            "body": {"data": encoded_body},
            "parts": [],
        },
        "internalDate": "1746000000000",
    }


def _make_llm_mock(response_json: dict) -> MagicMock:
    """
    Return a MagicMock that mimics the anthropic.Anthropic client.
    BaseAgent calls: self._client.messages.create(...) — synchronous call.
    """
    mock_content = MagicMock()
    mock_content.text = json.dumps(response_json)

    mock_message = MagicMock()
    mock_message.content = [mock_content]

    mock_messages = MagicMock()
    mock_messages.create = MagicMock(return_value=mock_message)

    mock_client = MagicMock()
    mock_client.messages = mock_messages

    return mock_client


# ---------------------------------------------------------------------------
# Test 1: Message is persisted after webhook ingestion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_message_persisted_after_webhook(async_session: AsyncSession, test_user):
    """
    handle_new_message should fetch the Gmail message, normalise it, and
    persist a Message row with the correct subject.
    """
    from app.ingestion.webhook_handler import handle_new_message
    from app.repositories.message_repo import MessageRepository

    gmail_id = "msg_test_001"
    fake_msg = _fake_gmail_message(gmail_id)

    with (
        patch(
            "app.ingestion.webhook_handler.GmailClient.__init__",
            return_value=None,
        ),
        patch(
            "app.ingestion.webhook_handler.GmailClient.get_message",
            return_value=fake_msg,
        ),
    ):
        await handle_new_message(
            gmail_message_id=gmail_id,
            user_id=str(test_user.id),
            db=async_session,
        )

    repo = MessageRepository(async_session)
    message = await repo.get_by_gmail_id(gmail_id, str(test_user.id))

    assert message is not None, "Message was not persisted to the database"
    assert message.subject == "Urgent: Q2 budget review by EOD"
    assert message.sender_email == "cfo@example.com"


# ---------------------------------------------------------------------------
# Test 2: Triage result is persisted after dispatching the triage agent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_triage_result_persisted(async_session: AsyncSession, test_user):
    """
    After handle_new_message + manual triage dispatch, a TriageResult row
    should exist with priority == 'urgent'.
    """
    from app.ingestion.webhook_handler import handle_new_message
    from app.orchestrator.state_machine import WorkflowStateMachine, WorkflowState
    from app.repositories.message_repo import MessageRepository
    from app.repositories.workflow_repo import WorkflowRepository, TriageRepository
    from app.models.message import TriagePriority

    gmail_id = "msg_test_002"
    fake_msg = _fake_gmail_message(gmail_id)

    triage_response = {
        "priority": "urgent",
        "confidence": 0.92,
        "rationale": "Test urgent",
        "labels": [],
    }
    llm_mock_client = _make_llm_mock(triage_response)

    with (
        patch(
            "app.ingestion.webhook_handler.GmailClient.__init__",
            return_value=None,
        ),
        patch(
            "app.ingestion.webhook_handler.GmailClient.get_message",
            return_value=fake_msg,
        ),
        # Patch the Anthropic client constructor used by BaseAgent.__init__
        patch(
            "app.agents.base_agent.anthropic.Anthropic",
            return_value=llm_mock_client,
        ),
    ):
        await handle_new_message(
            gmail_message_id=gmail_id,
            user_id=str(test_user.id),
            db=async_session,
        )

        # Fetch the WorkflowRun that was created
        msg_repo = MessageRepository(async_session)
        message = await msg_repo.get_by_gmail_id(gmail_id, str(test_user.id))
        assert message is not None

        wf_repo = WorkflowRepository(async_session)
        run = await wf_repo.get_by_message_id(str(message.id))
        assert run is not None

        # The run is in state "ingested"; advance to NORMALIZED so the FSM
        # can route to dispatch_triage (NORMALIZED → dispatch triage agent).
        fsm = WorkflowStateMachine(str(run.id), WorkflowState.INGESTED)
        await fsm.transition(WorkflowState.NORMALIZED, async_session)
        # dispatch_agents in NORMALIZED state calls dispatch_triage, which
        # transitions to TRIAGED and then calls dispatch_agents again.
        # For test 2 we only want triage; mock GmailClient for the draft
        # path too so it doesn't error if routing continues.
        # agent_dispatcher uses local imports, so patch the class on its
        # defining module (app.ingestion.gmail_client).
        with patch(
            "app.ingestion.gmail_client.GmailClient.__init__",
            return_value=None,
        ):
            with patch(
                "app.ingestion.gmail_client.GmailClient.create_draft",
                return_value="draft_skip",
            ):
                await fsm.dispatch_agents(async_session)

    # Assert TriageResult was persisted
    triage_repo = TriageRepository(async_session)
    run2 = await WorkflowRepository(async_session).get_by_message_id(str(message.id))
    triage = await triage_repo.get_by_workflow_run(str(run2.id))

    assert triage is not None, "TriageResult was not persisted"
    assert triage.priority == TriagePriority.urgent
    assert triage.confidence == pytest.approx(0.92, abs=1e-6)


# ---------------------------------------------------------------------------
# Test 3: Draft is created for an urgent message
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_created_for_urgent_message(async_session: AsyncSession, test_user):
    """
    For an urgent message the dispatcher should run DraftAgent and persist a
    Draft row after creating the Gmail draft.
    """
    from app.ingestion.webhook_handler import handle_new_message
    from app.orchestrator.state_machine import WorkflowStateMachine, WorkflowState
    from app.repositories.message_repo import MessageRepository
    from app.repositories.workflow_repo import WorkflowRepository
    from app.repositories.draft_repo import DraftRepository

    gmail_id = "msg_test_003"
    fake_msg = _fake_gmail_message(gmail_id)

    triage_response = {
        "priority": "urgent",
        "confidence": 0.95,
        "rationale": "Hard deadline, action required",
        "labels": [],
    }
    draft_response = {
        "draft_body": "Hi Jane, I'll have the numbers ready before 5pm. Best, Neel",
        "subject_line": "Re: Urgent: Q2 budget review by EOD",
        "confidence": 0.88,
    }

    # We need to make the LLM mock return different responses for triage vs
    # draft calls.  We do this by making create() a side_effect list.
    def _llm_side_effect(**kwargs):
        # Identify by max_tokens: triage uses 1024, draft uses 2048
        if kwargs.get("max_tokens", 1024) >= 2048:
            text = json.dumps(draft_response)
        else:
            text = json.dumps(triage_response)
        mock_content = MagicMock()
        mock_content.text = text
        mock_msg = MagicMock()
        mock_msg.content = [mock_content]
        return mock_msg

    mock_messages = MagicMock()
    mock_messages.create = MagicMock(side_effect=_llm_side_effect)
    llm_mock_client = MagicMock()
    llm_mock_client.messages = mock_messages

    with (
        patch(
            "app.ingestion.webhook_handler.GmailClient.__init__",
            return_value=None,
        ),
        patch(
            "app.ingestion.webhook_handler.GmailClient.get_message",
            return_value=fake_msg,
        ),
        patch(
            "app.agents.base_agent.anthropic.Anthropic",
            return_value=llm_mock_client,
        ),
        # agent_dispatcher uses local imports so patch on the defining module
        patch(
            "app.ingestion.gmail_client.GmailClient.__init__",
            return_value=None,
        ),
        patch(
            "app.ingestion.gmail_client.GmailClient.create_draft",
            return_value="draft_001",
        ),
    ):
        await handle_new_message(
            gmail_message_id=gmail_id,
            user_id=str(test_user.id),
            db=async_session,
        )

        msg_repo = MessageRepository(async_session)
        message = await msg_repo.get_by_gmail_id(gmail_id, str(test_user.id))
        assert message is not None

        wf_repo = WorkflowRepository(async_session)
        run = await wf_repo.get_by_message_id(str(message.id))
        assert run is not None

        fsm = WorkflowStateMachine(str(run.id), WorkflowState.INGESTED)
        await fsm.transition(WorkflowState.NORMALIZED, async_session)
        # dispatch_agents(NORMALIZED) → dispatch_triage → transitions to TRIAGED
        # → dispatch_agents(TRIAGED) → priority==urgent → dispatch_draft
        # → transitions to PENDING_REVIEW
        await fsm.dispatch_agents(async_session)

    # Assert Draft row was persisted
    draft_repo = DraftRepository(async_session)
    run2 = await WorkflowRepository(async_session).get_by_message_id(str(message.id))
    drafts = await draft_repo.get_pending_for_user(str(test_user.id))

    assert len(drafts) >= 1, "No Draft row was persisted for the urgent message"
    draft = drafts[0]
    assert draft.gmail_draft_id == "draft_001"
    assert draft.workflow_run_id == run2.id
