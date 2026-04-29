"""
Tests for JWT session management — token creation, validation, expiry, and
the get_current_user dependency.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from core.config import settings
from core.security.auth import (
    _ALGORITHM,
    _ISSUER,
    create_session_token,
    decode_session_token,
)


# ── Token creation ───────────────────────────────────────────────────────────


def test_create_session_token_returns_string():
    user_id = uuid.uuid4()
    token = create_session_token(user_id=user_id, email="test@example.com")
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_session_token_contains_claims():
    user_id = uuid.uuid4()
    token = create_session_token(user_id=user_id, email="test@example.com")
    claims = jwt.decode(
        token, settings.app_secret_key, algorithms=[_ALGORITHM], issuer=_ISSUER
    )
    assert claims["sub"] == str(user_id)
    assert claims["email"] == "test@example.com"
    assert claims["iss"] == _ISSUER
    assert "exp" in claims
    assert "iat" in claims


def test_session_token_has_72h_expiry():
    user_id = uuid.uuid4()
    before = datetime.now(tz=timezone.utc)
    token = create_session_token(user_id=user_id, email="a@b.com")
    claims = jwt.decode(
        token, settings.app_secret_key, algorithms=[_ALGORITHM], issuer=_ISSUER
    )
    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    assert exp > before + timedelta(hours=71)
    assert exp < before + timedelta(hours=73)


# ── Token decode / validation ────────────────────────────────────────────────


def test_decode_valid_token():
    user_id = uuid.uuid4()
    token = create_session_token(user_id=user_id, email="x@y.com")
    claims = decode_session_token(token)
    assert claims["sub"] == str(user_id)


def test_decode_expired_token_raises():
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@y.com",
        "iss": _ISSUER,
        "iat": datetime.now(tz=timezone.utc) - timedelta(hours=100),
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.app_secret_key, algorithm=_ALGORITHM)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_session_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_decode_tampered_token_raises():
    token = create_session_token(user_id=uuid.uuid4(), email="a@b.com")
    tampered = token[:-5] + "XXXXX"
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_session_token(tampered)
    assert exc_info.value.status_code == 401


def test_decode_wrong_issuer_raises():
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "x@y.com",
        "iss": "wrong-issuer",
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.app_secret_key, algorithm=_ALGORITHM)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        decode_session_token(token)


# ── Protected endpoint access ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client):
    """Endpoints using get_current_user should reject unauthenticated requests."""
    response = await client.get("/mailboxes/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_request_succeeds(authenticated_client):
    """Endpoints using get_current_user should accept valid Bearer tokens."""
    response = await authenticated_client.get("/mailboxes/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_expired_token_returns_401(client):
    """Expired tokens should be rejected."""
    payload = {
        "sub": str(uuid.UUID("00000000-0000-0000-0000-000000000001")),
        "email": "test@example.com",
        "iss": _ISSUER,
        "iat": datetime.now(tz=timezone.utc) - timedelta(hours=100),
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(payload, settings.app_secret_key, algorithm=_ALGORITHM)
    response = await client.get(
        "/mailboxes/",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401
