"""Shared test fixtures. Env vars must be set BEFORE any app imports."""
import os

# Set required env vars before any app module is imported.
# These are test-only dummies — never real credentials.
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("LLM_API_KEY", "test-llm-api-key")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-32-chars-long!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/inbox_chief_test")

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.ingestion.normalizer import NormalizedMessage
from app.telemetry.events import TelemetryEmitter


@pytest.fixture
def mock_telemetry() -> TelemetryEmitter:
    emitter = MagicMock(spec=TelemetryEmitter)
    emitter.emit = AsyncMock()
    emitter.emit_agent_call = AsyncMock()
    return emitter


@pytest.fixture
def sample_message() -> NormalizedMessage:
    return NormalizedMessage(
        message_id="msg_001",
        thread_id="thread_001",
        subject="Urgent: Q2 budget review by EOD",
        sender_email="cfo@example.com",
        sender_name="Jane CFO",
        received_at=datetime(2026, 4, 30, 9, 0, tzinfo=timezone.utc),
        body_preview="We need the updated numbers before the board call at 5pm. Action required.",
        has_attachments=False,
        label_ids=["INBOX"],
    )


@pytest.fixture
def sample_normal_message() -> NormalizedMessage:
    return NormalizedMessage(
        message_id="msg_002",
        thread_id="thread_002",
        subject="Team lunch next Friday",
        sender_email="colleague@example.com",
        sender_name="Alex",
        received_at=datetime(2026, 4, 30, 10, 0, tzinfo=timezone.utc),
        body_preview="Hey, want to grab lunch with the team next Friday? Let me know!",
        has_attachments=False,
        label_ids=["INBOX"],
    )
