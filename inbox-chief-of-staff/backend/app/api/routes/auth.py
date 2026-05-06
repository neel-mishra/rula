from __future__ import annotations
import asyncio
import base64
import functools
import hashlib
import secrets
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.security import encrypt_token, decrypt_token, create_session_token, verify_session_token
from app.ingestion.gmail_client import GmailClient
from app.repositories.user_repo import UserRepository, MailboxRepository


async def _run_sync(fn, *args, **kwargs):
    """Run a blocking function in the default thread pool without blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


async def _activate_gmail_watch(refresh_token: str, user_id: str) -> None:
    """Set up Gmail push watch in the background after OAuth redirect.

    Runs all sync googleapiclient/requests calls in a thread so the event loop
    is never blocked. Uses its own DB session since the request session is gone.
    """
    from datetime import datetime, timezone
    from app.core.db import AsyncSessionLocal
    from app.repositories.user_repo import MailboxRepository

    try:
        def _sync_watch() -> dict:
            client = GmailClient(refresh_token)
            return client.setup_watch(settings.pubsub_topic)

        watch_response = await _run_sync(_sync_watch)
        expiry_dt = datetime.fromtimestamp(
            int(watch_response["expiration"]) / 1000, tz=timezone.utc
        )
        async with AsyncSessionLocal() as db:
            mailbox_repo = MailboxRepository(db)
            mailbox = await mailbox_repo.get_by_user(user_id)
            if mailbox:
                await mailbox_repo.update_watch_expiry(mailbox, expiry_dt)
        logger.info("gmail_watch_registered", user_id=user_id, expiry=expiry_dt.isoformat())
    except Exception as exc:
        logger.warning("gmail_watch_failed", user_id=user_id, error=str(exc))

logger = structlog.get_logger()
router = APIRouter()

SCOPES = [s.strip() for s in settings.gmail_scopes.split(",")]


async def get_current_user_id(request: Request) -> str:
    """FastAPI dependency: extract and verify session cookie → user_id."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user_id


def _build_flow() -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uris": [settings.google_oauth_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
    )


def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(96)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/login")
async def login() -> RedirectResponse:
    code_verifier, code_challenge = _pkce_pair()
    flow = _build_flow()
    # Carry the verifier in `state` — Google echoes it back unchanged, so no
    # cookie is needed and there are no cross-domain/SameSite issues.
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
        state=code_verifier,
    )
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    request: Request,
    background_tasks: BackgroundTasks,
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if error or not code:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error or 'missing code'}")

    # `state` carries the PKCE code_verifier set in /login.
    if not state:
        raise HTTPException(status_code=400, detail="Missing state — restart the OAuth flow.")
    code_verifier = state

    try:
        flow = _build_flow()
        # Run in executor: fetch_token uses requests (sync) and blocks the event loop.
        await _run_sync(flow.fetch_token, code=code, code_verifier=code_verifier)

        # Pull tokens directly from the session dict to avoid credential-wrapping surprises.
        token_data = flow.oauth2session.token
        access_token: str = token_data["access_token"]
        refresh_token: str | None = token_data.get("refresh_token")
        logger.info("oauth_token_exchanged", has_refresh=bool(refresh_token))

        if not refresh_token:
            raise HTTPException(status_code=400, detail="No refresh token returned. Revoke app access and retry.")

        # Gmail profile — works with gmail.readonly; no extra scope needed.
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            profile = resp.json()
        email: str = profile["emailAddress"]
        logger.info("oauth_email_resolved", email=email)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("oauth_callback_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {exc}")

    # Upsert user
    user_repo = UserRepository(db)
    mailbox_repo = MailboxRepository(db)

    encrypted_token = encrypt_token(refresh_token)
    existing = await user_repo.get_by_email(email)
    if existing:
        user = await user_repo.update_refresh_token(existing, encrypted_token)
    else:
        user = await user_repo.create(email=email, encrypted_refresh_token=encrypted_token)

    mailbox = await mailbox_repo.upsert(user_id=str(user.id), gmail_address=email)

    # Schedule Gmail watch setup as a background task so it doesn't block the redirect.
    # GmailClient uses sync HTTP (requests + httplib2) which would stall the event loop inline.
    if settings.pubsub_topic:
        background_tasks.add_task(_activate_gmail_watch, refresh_token, str(user.id))

    # Set session cookie
    session_token = create_session_token(str(user.id))
    redirect = RedirectResponse(url=f"{settings.app_base_url}/inbox", status_code=302)
    redirect.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        secure=settings.node_env == "production",
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # 30 days
    )
    logger.info("User authenticated", email=email, user_id=str(user.id))
    return redirect


@router.get("/me")
async def me(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": str(user.id), "email": user.email, "timezone": user.timezone}


@router.delete("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie("session")
    return {"status": "logged_out"}
