from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from core.models.mailbox import Mailbox
from core.models.user import User


def _pubsub_body(notification: dict) -> bytes:
    payload = {
        "message": {
            "data": base64.b64encode(
                json.dumps(notification).encode("utf-8")
            ).decode("utf-8")
        }
    }
    return json.dumps(payload).encode("utf-8")


def _hmac_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


@pytest.fixture
async def webhook_mailbox(db_session):
    user = User(
        id=uuid.uuid4(),
        email="webhook-user@example.com",
        display_name="Webhook User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    mailbox = Mailbox(
        id=uuid.uuid4(),
        user_id=user.id,
        gmail_email="webhook@gmail.com",
        gmail_user_id="webhook@gmail.com",
        gmail_history_id="101",
        is_active=True,
        is_connected=True,
    )
    db_session.add(mailbox)
    await db_session.flush()
    return mailbox


@pytest.mark.asyncio
async def test_gmail_webhook_valid_bearer_token(client, db_session, webhook_mailbox, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "secret-token")
    body = _pubsub_body({"emailAddress": webhook_mailbox.gmail_email, "historyId": "202"})

    @asynccontextmanager
    async def _session_override():
        yield db_session

    with patch("api.routers.webhooks.get_db_session", _session_override), patch(
        "api.routers.webhooks._dispatch_ingest_job", new=AsyncMock()
    ) as dispatch_mock:
        response = await client.post(
            "/webhooks/gmail",
            content=body,
            headers={
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert "correlation_id" in response.json()
    assert dispatch_mock.await_count == 1


@pytest.mark.asyncio
async def test_gmail_webhook_invalid_bearer_token_forbidden(client, webhook_mailbox, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "secret-token")
    body = _pubsub_body({"emailAddress": webhook_mailbox.gmail_email, "historyId": "202"})

    response = await client.post(
        "/webhooks/gmail",
        content=body,
        headers={
            "Authorization": "Bearer wrong-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid authorization token"}


@pytest.mark.asyncio
async def test_gmail_webhook_valid_hmac_without_auth_header(
    client, db_session, webhook_mailbox, monkeypatch
):
    secret = "secret-token"
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", secret)
    body = _pubsub_body({"emailAddress": webhook_mailbox.gmail_email, "historyId": "303"})
    signature = _hmac_signature(secret, body)

    @asynccontextmanager
    async def _session_override():
        yield db_session

    with patch("api.routers.webhooks.get_db_session", _session_override), patch(
        "api.routers.webhooks._dispatch_ingest_job", new=AsyncMock()
    ) as dispatch_mock:
        response = await client.post(
            "/webhooks/gmail",
            content=body,
            headers={
                "X-Goog-Signature": signature,
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert "correlation_id" in response.json()
    assert dispatch_mock.await_count == 1


@pytest.mark.asyncio
async def test_gmail_webhook_invalid_hmac_forbidden(client, webhook_mailbox, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "secret-token")
    body = _pubsub_body({"emailAddress": webhook_mailbox.gmail_email, "historyId": "303"})

    response = await client.post(
        "/webhooks/gmail",
        content=body,
        headers={
            "X-Goog-Signature": "bad-signature",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid signature"}


@pytest.mark.asyncio
async def test_gmail_webhook_malformed_json_returns_400(client, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "")

    response = await client.post(
        "/webhooks/gmail",
        content=b'{"message":',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid JSON"}


@pytest.mark.asyncio
async def test_gmail_webhook_malformed_base64_payload_returns_400(client, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "")
    payload = {"message": {"data": "%%%not-valid-base64%%%"}}

    response = await client.post("/webhooks/gmail", json=payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Cannot decode notification data"}


@pytest.mark.asyncio
async def test_gmail_webhook_missing_email_address_path(client, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "")
    body = _pubsub_body({"historyId": "404"})

    response = await client.post(
        "/webhooks/gmail",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "missing_email_address"}


@pytest.mark.asyncio
async def test_gmail_webhook_mailbox_not_found_path(client, db_session, monkeypatch):
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "")
    body = _pubsub_body({"emailAddress": "unknown@gmail.com", "historyId": "505"})

    @asynccontextmanager
    async def _session_override():
        yield db_session

    with patch("api.routers.webhooks.get_db_session", _session_override):
        response = await client.post(
            "/webhooks/gmail",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "mailbox_not_found"}
