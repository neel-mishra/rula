"""Integration tests for SES inbound assistant endpoint."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from api.main import app
from core.db import get_db
from core.models.assistant_conversation import (
    AssistantConversation,
    AssistantMessage,
)
from core.models.user import User


def _raw_email(from_addr: str, subject: str, body: str) -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"To: assistant@inbox.example.com\r\n"
        f"Subject: {subject}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode()


def _sns_envelope(sender: str, subject: str, body: str) -> dict:
    ses_payload = {
        "notificationType": "Received",
        "mail": {
            "source": sender,
            "commonHeaders": {
                "from": [sender],
                "subject": subject,
            },
        },
        "content": base64.b64encode(_raw_email(sender, subject, body)).decode(),
    }
    return {
        "Type": "Notification",
        "Message": json.dumps(ses_payload),
    }


@pytest_asyncio.fixture
async def inbound_client(db_session):
    async def override_get_db():
        yield db_session

    user = User(
        email="owner@example.com",
        display_name="Owner",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, user
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ses_inbound_creates_conversation(inbound_client, db_session, monkeypatch):
    ac, user = inbound_client

    # Stub PolicyAgent to avoid hitting real LLM
    from subagents.policy import PolicyAgent
    from core.schemas.contracts import AgentResponse, PolicyCompileResult, StageMeta

    async def fake_run(self, task):
        return AgentResponse[PolicyCompileResult](
            ok=True,
            payload=PolicyCompileResult(
                rules_created=1,
                rules_updated=0,
                policy_version="v1",
                needs_clarification=False,
                clarification_question=None,
            ),
            warnings=[],
            meta=StageMeta(
                run_id=task.run_id,
                correlation_id=task.correlation_id,
                stage="policy",
                started_at=datetime.now(tz=timezone.utc),
            ),
        )

    monkeypatch.setattr(PolicyAgent, "run", fake_run)

    envelope = _sns_envelope(
        "owner@example.com",
        "archive marketing",
        "Always archive emails from @news.example.com",
    )
    resp = await ac.post("/webhooks/ses-inbound", json=envelope)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["rules_created"] == 1

    conv_id = data["conversation_id"]
    conv = await db_session.execute(
        select(AssistantConversation).where(AssistantConversation.id == conv_id)
    )
    conversation = conv.scalar_one()
    assert conversation.user_id == user.id

    msgs = await db_session.execute(
        select(AssistantMessage).where(
            AssistantMessage.conversation_id == conversation.id
        )
    )
    messages = msgs.scalars().all()
    assert len(messages) == 2
    assert any(m.role == "user" and "archive" in m.content for m in messages)
    assert any(m.role == "assistant" for m in messages)


@pytest.mark.asyncio
async def test_ses_inbound_unknown_sender_is_rejected(inbound_client):
    ac, _user = inbound_client
    envelope = _sns_envelope(
        "stranger@other.com", "hi", "ignore me",
    )
    resp = await ac.post("/webhooks/ses-inbound", json=envelope)
    assert resp.status_code == 200
    assert resp.json()["status"] == "unknown_sender"


@pytest.mark.asyncio
async def test_ses_inbound_missing_sender_400(inbound_client):
    ac, _user = inbound_client
    envelope = {
        "Type": "Notification",
        "Message": json.dumps(
            {"notificationType": "Received", "mail": {"commonHeaders": {}}}
        ),
    }
    resp = await ac.post("/webhooks/ses-inbound", json=envelope)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ses_inbound_secret_gate(inbound_client, monkeypatch):
    ac, _user = inbound_client
    from core.config import settings as cfg
    monkeypatch.setattr(cfg, "ses_inbound_secret", "secret-123")

    envelope = _sns_envelope(
        "owner@example.com", "hi", "archive newsletters",
    )

    # No auth header
    resp = await ac.post("/webhooks/ses-inbound", json=envelope)
    assert resp.status_code == 403

    # Bad auth header
    resp = await ac.post(
        "/webhooks/ses-inbound",
        json=envelope,
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 403
