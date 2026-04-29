"""
Gmail mailbox connect/disconnect operations.

This router is intentionally separate from auth:
- auth = who you are
- mailbox_connect = which inboxes are linked to your account

OAuth callback URL is **backend-direct**: set ``GOOGLE_REDIRECT_URI`` to the
public API origin, e.g. ``https://<render-api>/mailbox-connect/gmail/callback``,
and register the same URL in Google Cloud Console. The SPA may use
``/auth/callback`` only if you later align Google redirect to that path,
which requires a matching backend route or proxy — for MVP, prefer the API URL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.gmail.auth import exchange_code_for_tokens, get_authorization_url
from core.models.mailbox import Mailbox
from core.models.user import User
from core.security.auth import get_current_user
from core.security.csrf import generate_oauth_state, validate_oauth_state

log = structlog.get_logger(__name__)

router = APIRouter()


class ConnectResponse(BaseModel):
    authorization_url: str
    state: str


class CallbackResponse(BaseModel):
    mailbox_id: str
    gmail_email: str
    connected: bool


class DisconnectResponse(BaseModel):
    mailbox_id: str
    disconnected: bool


@router.get("/gmail/connect", response_model=ConnectResponse)
async def gmail_connect(_: User = Depends(get_current_user)) -> ConnectResponse:
    state = await generate_oauth_state()
    url = get_authorization_url(state=state)
    return ConnectResponse(authorization_url=url, state=state)


@router.get("/gmail/callback", response_model=CallbackResponse)
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CallbackResponse:
    stored_value = await validate_oauth_state(state)
    if stored_value is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    try:
        token_data = exchange_code_for_tokens(code=code, state=state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    from core.config import settings
    from core.security import decrypt_token

    temp_refresh = decrypt_token(token_data["encrypted_refresh_token"])
    creds = Credentials(
        token=None,
        refresh_token=temp_refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=settings.google_scopes_list,
    )

    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        gmail_email = profile.get("emailAddress", "")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gmail profile fetch failed: {exc}")

    existing_result = await db.execute(
        select(Mailbox).where(
            Mailbox.user_id == user.id,
            Mailbox.gmail_email == gmail_email,
        )
    )
    mailbox = existing_result.scalar_one_or_none()
    if mailbox is None:
        mailbox = Mailbox(
            id=uuid.uuid4(),
            user_id=user.id,
            gmail_email=gmail_email,
            gmail_user_id=gmail_email,
            encrypted_refresh_token=token_data["encrypted_refresh_token"],
            encrypted_access_token=token_data["encrypted_access_token"],
            token_expiry=token_data["token_expiry"],
            is_active=True,
            is_connected=True,
        )
        db.add(mailbox)
        await db.flush()
    else:
        mailbox.encrypted_refresh_token = token_data["encrypted_refresh_token"]
        mailbox.encrypted_access_token = token_data["encrypted_access_token"]
        mailbox.token_expiry = token_data["token_expiry"]
        mailbox.is_active = True
        mailbox.is_connected = True

    from core.config import settings as cfg

    try:
        from core.gmail import GmailClient

        client = GmailClient(mailbox)
        label_ids = client.ensure_system_labels()
        mailbox.label_needs_attention = label_ids.get("needs_attention")
        mailbox.label_next_brief = label_ids.get("next_brief")
        mailbox.label_cora_system = label_ids.get("cora_system")

        if cfg.gmail_webhook_topic:
            watch_result = client.register_watch(topic_name=cfg.gmail_webhook_topic)
            expiry_ms = watch_result.get("expiration")
            if expiry_ms:
                mailbox.gmail_watch_expiration = datetime.fromtimestamp(
                    int(expiry_ms) / 1000, tz=timezone.utc
                )
            mailbox.gmail_watch_resource_id = watch_result.get("resourceId")
            mailbox.gmail_history_id = str(watch_result.get("historyId", ""))
    except Exception as exc:
        log.warning("mailbox_setup_partial_failure", error=str(exc))

    return CallbackResponse(
        mailbox_id=str(mailbox.id),
        gmail_email=gmail_email,
        connected=True,
    )


@router.post("/gmail/disconnect/{mailbox_id}", response_model=DisconnectResponse)
async def gmail_disconnect(
    mailbox_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DisconnectResponse:
    mailbox = await db.get(Mailbox, mailbox_id)
    if not mailbox:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    if mailbox.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your mailbox")

    try:
        from core.gmail import GmailClient

        client = GmailClient(mailbox)
        client.stop_watch()
    except Exception:
        pass

    try:
        from core.gmail.auth import revoke_token

        await revoke_token(mailbox)
    except Exception:
        pass

    mailbox.is_active = False
    mailbox.is_connected = False
    mailbox.encrypted_refresh_token = None
    mailbox.encrypted_access_token = None

    return DisconnectResponse(mailbox_id=str(mailbox_id), disconnected=True)
