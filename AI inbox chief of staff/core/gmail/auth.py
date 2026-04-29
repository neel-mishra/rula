"""
Gmail OAuth 2.0 flow.
Scopes: readonly + labels + modify + compose (NO gmail.send).
Refresh tokens stored encrypted via encryption.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from core.config import settings
from core.security import decrypt_token, encrypt_token

log = structlog.get_logger(__name__)

# Explicitly assert: gmail.send is never in scopes
_REQUIRED_SCOPES = settings.google_scopes_list
assert not any(
    "gmail.send" in s for s in _REQUIRED_SCOPES
), "gmail.send scope MUST NOT be requested — no auto-send capability"


def build_oauth_flow(state: str | None = None) -> Flow:
    """Create a Google OAuth2 Flow for the Gmail API."""
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config=client_config,
        scopes=_REQUIRED_SCOPES,
        redirect_uri=settings.google_redirect_uri,
        state=state,
    )
    return flow


def get_authorization_url(state: str) -> str:
    """Return the OAuth consent URL. State is a CSRF-protected nonce tied to the session."""
    flow = build_oauth_flow(state=state)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",  # always request fresh scopes
        prompt="consent",                 # force refresh token every time
    )
    return url


def exchange_code_for_tokens(code: str, state: str) -> dict[str, Any]:
    """
    Exchange authorization code for access + refresh tokens.
    Returns dict with encrypted tokens and metadata.
    """
    flow = build_oauth_flow(state=state)
    flow.fetch_token(code=code)

    credentials: Credentials = flow.credentials

    # Validate scopes
    granted = set(credentials.scopes or [])
    required = set(_REQUIRED_SCOPES)
    if not required.issubset(granted):
        missing = required - granted
        raise ValueError(f"Missing required OAuth scopes: {missing}")

    # Explicitly verify no send scope was granted
    assert "https://www.googleapis.com/auth/gmail.send" not in granted, (
        "gmail.send scope must never be granted"
    )

    encrypted_refresh = encrypt_token(credentials.refresh_token) if credentials.refresh_token else None
    encrypted_access = encrypt_token(credentials.token) if credentials.token else None

    return {
        "encrypted_refresh_token": encrypted_refresh,
        "encrypted_access_token": encrypted_access,
        "token_expiry": credentials.expiry,
        "granted_scopes": list(granted),
    }


def build_credentials_from_mailbox(mailbox: Any) -> Credentials:
    """
    Reconstruct Google Credentials from a Mailbox record.
    Decrypts stored tokens.
    """
    refresh_token = decrypt_token(mailbox.encrypted_refresh_token) if mailbox.encrypted_refresh_token else None
    access_token = decrypt_token(mailbox.encrypted_access_token) if mailbox.encrypted_access_token else None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=_REQUIRED_SCOPES,
    )

    if mailbox.token_expiry:
        creds.expiry = mailbox.token_expiry

    return creds


async def refresh_token_if_needed(mailbox: Any) -> bool:
    """
    Proactively refresh OAuth token if expiring within 10 minutes.
    Updates mailbox record with new encrypted tokens.
    Returns True if token was refreshed.
    """
    from datetime import timedelta
    from google.auth.transport.requests import Request

    if not mailbox.token_expiry:
        return False

    refresh_threshold = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
    if mailbox.token_expiry > refresh_threshold:
        return False

    try:
        creds = build_credentials_from_mailbox(mailbox)
        creds.refresh(Request())

        mailbox.encrypted_access_token = encrypt_token(creds.token) if creds.token else None
        mailbox.token_expiry = creds.expiry
        log.info("oauth.token_refreshed", mailbox_id=str(mailbox.id))
        return True
    except Exception as exc:
        log.error("oauth.token_refresh_failed", mailbox_id=str(mailbox.id), error=str(exc))
        return False


async def revoke_token(mailbox: Any) -> bool:
    """Revoke OAuth credentials with Google. Best-effort."""
    import httpx

    refresh_token = decrypt_token(mailbox.encrypted_refresh_token) if mailbox.encrypted_refresh_token else None
    if not refresh_token:
        return False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": refresh_token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if response.status_code == 200:
                log.info("oauth.token_revoked", mailbox_id=str(mailbox.id))
                return True
            else:
                log.warning("oauth.revoke_failed", status=response.status_code)
                return False
    except Exception as exc:
        log.error("oauth.revoke_error", error=str(exc))
        return False
