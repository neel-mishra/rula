from __future__ import annotations

import base64
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.models.mailbox import Mailbox
from core.models.user import User
from core.security.auth import create_session_token


def _auth_headers(user_id: uuid.UUID, email: str) -> dict[str, str]:
    token = create_session_token(user_id=user_id, email=email)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_phase5_auth_and_mailbox_connect_smoke(client, db_session):
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "smoke@example.com",
            "password": "supersecure123",
            "display_name": "Smoke",
        },
    )
    assert register_resp.status_code == 201
    token = register_resp.json()["session_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    me_resp = await client.get("/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200
    user_id = uuid.UUID(me_resp.json()["id"])

    list_before = await client.get("/mailboxes/", headers=auth_headers)
    assert list_before.status_code == 200
    assert list_before.json() == []

    with patch(
        "api.routers.mailbox_connect.generate_oauth_state",
        new=AsyncMock(return_value="state-xyz"),
    ), patch(
        "api.routers.mailbox_connect.get_authorization_url",
        return_value="https://accounts.google.com/o/oauth2/auth?state=state-xyz",
    ):
        connect_resp = await client.get("/mailbox-connect/gmail/connect", headers=auth_headers)
    assert connect_resp.status_code == 200
    assert connect_resp.json()["state"] == "state-xyz"

    fake_profile = {"emailAddress": "connected@gmail.com", "historyId": "101"}
    fake_service = SimpleNamespace(
        users=lambda: SimpleNamespace(
            getProfile=lambda userId: SimpleNamespace(execute=lambda: fake_profile)
        )
    )
    fake_gmail_client = SimpleNamespace(
        ensure_system_labels=lambda: {
            "needs_attention": "label-1",
            "next_brief": "label-2",
            "cora_system": "label-3",
        },
        register_watch=lambda topic_name: {
            "expiration": "1893456000000",
            "resourceId": "res-1",
            "historyId": "102",
        },
    )

    with patch(
        "api.routers.mailbox_connect.validate_oauth_state",
        new=AsyncMock(return_value="ok"),
    ), patch(
        "api.routers.mailbox_connect.exchange_code_for_tokens",
        return_value={
            "encrypted_refresh_token": "enc-refresh",
            "encrypted_access_token": "enc-access",
            "token_expiry": None,
        },
    ), patch(
        "core.security.decrypt_token",
        return_value="refresh-token",
    ), patch(
        "googleapiclient.discovery.build",
        return_value=fake_service,
    ), patch(
        "core.gmail.GmailClient",
        return_value=fake_gmail_client,
    ):
        callback_resp = await client.get(
            "/mailbox-connect/gmail/callback?code=fake-code&state=state-xyz",
            headers=auth_headers,
        )
    assert callback_resp.status_code == 200
    assert callback_resp.json()["connected"] is True
    mailbox_id = callback_resp.json()["mailbox_id"]

    list_after = await client.get("/mailboxes/", headers=auth_headers)
    assert list_after.status_code == 200
    assert len(list_after.json()) == 1
    assert list_after.json()[0]["id"] == mailbox_id
    assert list_after.json()[0]["gmail_email"] == "connected@gmail.com"

    # Disconnect should succeed for owner.
    disconnect_resp = await client.post(
        f"/mailbox-connect/gmail/disconnect/{mailbox_id}",
        headers=auth_headers,
    )
    assert disconnect_resp.status_code == 200
    assert disconnect_resp.json()["disconnected"] is True


@pytest.mark.asyncio
async def test_phase5_webhook_dispatch_smoke(client, db_session, monkeypatch):
    user = User(
        id=uuid.uuid4(),
        email="webhook@example.com",
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
        gmail_history_id="100",
        is_active=True,
        is_connected=True,
    )
    db_session.add(mailbox)
    await db_session.flush()

    notification = {
        "emailAddress": "webhook@gmail.com",
        "historyId": "200",
    }
    payload = {
        "message": {"data": base64.b64encode(json.dumps(notification).encode("utf-8")).decode("utf-8")}
    }
    monkeypatch.setattr("api.routers.webhooks.settings.gmail_webhook_secret", "")

    @asynccontextmanager
    async def _session_override():
        yield db_session

    with patch(
        "api.routers.webhooks._dispatch_ingest_job",
        new=AsyncMock(),
    ) as dispatch_mock, patch(
        "api.routers.webhooks.get_db_session",
        _session_override,
    ):
        resp = await client.post(
            "/webhooks/gmail",
            json=payload,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert dispatch_mock.await_count == 1
