from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.models.mailbox import Mailbox


@pytest.mark.asyncio
async def test_register_login_me_logout_flow(client):
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "phase4b@example.com",
            "password": "supersecure123",
            "display_name": "Phase 4B",
        },
    )
    assert register_resp.status_code == 201
    payload = register_resp.json()
    assert "session_token" in payload
    assert payload["user"]["email"] == "phase4b@example.com"

    token = payload["session_token"]
    me_resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "phase4b@example.com"

    login_resp = await client.post(
        "/auth/login",
        json={"email": "phase4b@example.com", "password": "supersecure123"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["user"]["email"] == "phase4b@example.com"

    logout_resp = await client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["logged_out"] is True


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(client):
    await client.post(
        "/auth/register",
        json={"email": "invalidpass@example.com", "password": "correctpass123"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "invalidpass@example.com", "password": "wrongpass123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mailbox_connect_requires_auth(client):
    resp = await client.get("/mailbox-connect/gmail/connect")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mailbox_connect_returns_oauth_url_when_authenticated(authenticated_client):
    with patch(
        "api.routers.mailbox_connect.generate_oauth_state",
        new=AsyncMock(return_value="state-123"),
    ), patch(
        "api.routers.mailbox_connect.get_authorization_url",
        return_value="https://accounts.google.com/o/oauth2/auth?state=state-123",
    ):
        resp = await authenticated_client.get("/mailbox-connect/gmail/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "state-123"
    assert "accounts.google.com" in data["authorization_url"]


@pytest.mark.asyncio
async def test_disconnect_rejects_non_owner(client, db_session):
    from core.models.user import User
    from core.security.auth import create_session_token

    owner = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        display_name="Owner",
        is_active=True,
    )
    other = User(
        id=uuid.uuid4(),
        email="other@example.com",
        display_name="Other",
        is_active=True,
    )
    db_session.add(owner)
    db_session.add(other)
    await db_session.flush()

    mailbox = Mailbox(
        id=uuid.uuid4(),
        user_id=owner.id,
        gmail_email="owner@gmail.com",
        gmail_user_id="owner@gmail.com",
        is_active=True,
        is_connected=True,
    )
    db_session.add(mailbox)
    await db_session.flush()

    token = create_session_token(user_id=other.id, email=other.email)
    resp = await client.post(
        f"/mailbox-connect/gmail/disconnect/{mailbox.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


class _FakeProfileRequest:
    def __init__(self, profile: dict | None = None, error: Exception | None = None):
        self._profile = profile or {}
        self._error = error

    def execute(self):
        if self._error:
            raise self._error
        return self._profile


class _FakeUsersResource:
    def __init__(self, profile: dict | None = None, error: Exception | None = None):
        self._profile = profile
        self._error = error

    def getProfile(self, userId: str):
        assert userId == "me"
        return _FakeProfileRequest(profile=self._profile, error=self._error)


class _FakeGmailService:
    def __init__(self, profile: dict | None = None, error: Exception | None = None):
        self._profile = profile
        self._error = error

    def users(self):
        return _FakeUsersResource(profile=self._profile, error=self._error)


@pytest.mark.asyncio
async def test_gmail_callback_rejects_invalid_or_expired_state(authenticated_client):
    with patch(
        "api.routers.mailbox_connect.validate_oauth_state",
        new=AsyncMock(return_value=None),
    ):
        resp = await authenticated_client.get(
            "/mailbox-connect/gmail/callback",
            params={"code": "fake-code", "state": "expired-state"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired OAuth state"


@pytest.mark.asyncio
async def test_gmail_callback_returns_400_when_token_exchange_fails(authenticated_client):
    with patch(
        "api.routers.mailbox_connect.validate_oauth_state",
        new=AsyncMock(return_value="ok"),
    ), patch(
        "api.routers.mailbox_connect.exchange_code_for_tokens",
        side_effect=ValueError("Token exchange failed"),
    ):
        resp = await authenticated_client.get(
            "/mailbox-connect/gmail/callback",
            params={"code": "bad-code", "state": "valid-state"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Token exchange failed"


@pytest.mark.asyncio
async def test_gmail_callback_returns_502_when_profile_fetch_fails(authenticated_client):
    token_data = {
        "encrypted_refresh_token": "enc-refresh",
        "encrypted_access_token": "enc-access",
        "token_expiry": datetime.now(timezone.utc),
    }
    with patch(
        "api.routers.mailbox_connect.validate_oauth_state",
        new=AsyncMock(return_value="ok"),
    ), patch(
        "api.routers.mailbox_connect.exchange_code_for_tokens",
        return_value=token_data,
    ), patch(
        "core.security.decrypt_token",
        return_value="refresh-token",
    ), patch(
        "googleapiclient.discovery.build",
        return_value=_FakeGmailService(error=RuntimeError("gmail profile error")),
    ):
        resp = await authenticated_client.get(
            "/mailbox-connect/gmail/callback",
            params={"code": "good-code", "state": "valid-state"},
        )

    assert resp.status_code == 502
    assert "Gmail profile fetch failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_gmail_callback_watch_registration_partial_failure_logs_warning_and_succeeds(
    authenticated_client, db_session
):
    token_data = {
        "encrypted_refresh_token": "enc-refresh",
        "encrypted_access_token": "enc-access",
        "token_expiry": datetime.now(timezone.utc),
    }

    fake_gmail_client = type(
        "FakeGmailClient",
        (),
        {
            "__init__": lambda self, mailbox: None,
            "ensure_system_labels": lambda self: {
                "needs_attention": "lbl-needs",
                "next_brief": "lbl-brief",
                "cora_system": "lbl-system",
            },
            "register_watch": lambda self, topic_name: (_ for _ in ()).throw(
                RuntimeError("watch registration failed")
            ),
        },
    )

    with patch(
        "api.routers.mailbox_connect.validate_oauth_state",
        new=AsyncMock(return_value="ok"),
    ), patch(
        "api.routers.mailbox_connect.exchange_code_for_tokens",
        return_value=token_data,
    ), patch(
        "core.security.decrypt_token",
        return_value="refresh-token",
    ), patch(
        "googleapiclient.discovery.build",
        return_value=_FakeGmailService(profile={"emailAddress": "watchfail@example.com"}),
    ), patch(
        "core.config.settings.gmail_webhook_topic",
        "projects/test/topics/gmail-webhook",
    ), patch(
        "core.gmail.GmailClient",
        fake_gmail_client,
    ), patch(
        "api.routers.mailbox_connect.log.warning",
    ) as warning_mock:
        resp = await authenticated_client.get(
            "/mailbox-connect/gmail/callback",
            params={"code": "good-code", "state": "valid-state"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["gmail_email"] == "watchfail@example.com"
    warning_mock.assert_called_once()
    assert warning_mock.call_args.args[0] == "mailbox_setup_partial_failure"

    mailbox = await db_session.get(Mailbox, uuid.UUID(data["mailbox_id"]))
    assert mailbox is not None
    assert mailbox.is_connected is True
    assert mailbox.gmail_email == "watchfail@example.com"
