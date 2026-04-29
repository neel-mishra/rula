"""Unit tests for typed stage contracts — validates schema correctness."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from core.schemas.contracts import (
    IngestionTask,
    TaskContext,
    TriageTask,
    SafetyCheckTask,
    DraftTask,
    AgentResponse,
    ErrorEnvelope,
    StageMeta,
)


class TestTaskContext:
    def test_required_fields(self):
        ctx = TaskContext(
            user_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            correlation_id="test-correlation-id",
            policy_version="v1",
        )
        assert ctx.run_id is not None
        assert ctx.policy_version == "v1"

    def test_missing_user_id_raises(self):
        with pytest.raises(ValidationError):
            TaskContext(
                mailbox_id=uuid.uuid4(),
                correlation_id="test",
            )

    def test_missing_mailbox_id_raises(self):
        with pytest.raises(ValidationError):
            TaskContext(
                user_id=uuid.uuid4(),
                correlation_id="test",
            )


class TestIngestionTask:
    def test_valid_ingestion_task(self):
        task = IngestionTask(
            user_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            correlation_id="corr-123",
            policy_version="v1",
            gmail_message_id="msg_abc123",
            gmail_history_id="12345",
        )
        assert task.gmail_message_id == "msg_abc123"
        assert task.is_backfill is False


class TestTriageTask:
    def test_valid_triage_task(self):
        email_id = uuid.uuid4()
        task = TriageTask(
            user_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            correlation_id="corr-456",
            policy_version="v1",
            email_id=email_id,
            gmail_message_id="msg_xyz",
        )
        assert task.email_id == email_id


class TestAgentResponse:
    def test_success_response(self):
        now = datetime.now(tz=timezone.utc)
        response = AgentResponse(
            ok=True,
            payload={"result": "ok"},
            warnings=[],
            meta=StageMeta(
                run_id="run-1",
                correlation_id="corr-1",
                stage="test_stage",
                started_at=now,
                duration_ms=42.5,
            ),
        )
        assert response.ok is True
        assert response.error is None

    def test_error_response(self):
        now = datetime.now(tz=timezone.utc)
        response = AgentResponse(
            ok=False,
            payload=None,
            error=ErrorEnvelope(
                code="TEST_ERROR",
                message="Something failed",
                stage="test_stage",
                recoverable=True,
            ),
            meta=StageMeta(
                run_id="run-2",
                correlation_id="corr-2",
                stage="test_stage",
                started_at=now,
            ),
        )
        assert response.ok is False
        assert response.error.code == "TEST_ERROR"
        assert response.error.recoverable is True


class TestMailboxIsolationInContracts:
    """Every contract must carry mailbox_id — test isolation fields present."""

    def test_ingestion_task_has_mailbox_id(self):
        task = IngestionTask(
            user_id=uuid.uuid4(),
            mailbox_id=uuid.uuid4(),
            correlation_id="c",
            policy_version="v1",
            gmail_message_id="m",
            gmail_history_id="h",
        )
        assert task.mailbox_id is not None
        assert task.user_id is not None
        assert task.correlation_id is not None
        assert task.policy_version is not None
