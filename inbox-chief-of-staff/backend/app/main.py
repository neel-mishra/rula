"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import functools
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

# Load .env into os.environ early so libs like requests_oauthlib see the flags.
from dotenv import load_dotenv
load_dotenv()

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_

from app.core.config import settings
from app.core.db import init_db, AsyncSessionLocal
from app.api.routes import auth, messages, drafts, briefs, webhooks, health, feedback, worker
from app.policy.action_policy import PolicyViolationError

logger = structlog.get_logger(__name__)

_WATCH_RENEWAL_INTERVAL_SECONDS = 6 * 60 * 60  # 6 hours
_WATCH_RENEWAL_HORIZON = timedelta(hours=24)


async def _renew_expiring_watches() -> None:
    """Renew Gmail push watches for any active connection that is expired or
    expiring within the next 24 hours.

    Runs sync GmailClient calls in a thread pool so the event loop is not blocked.
    Failures per-connection are logged and swallowed so one bad token doesn't
    abort renewal for the rest.
    """
    if not settings.pubsub_topic:
        return

    from app.models.user import MailboxConnection, MailboxStatus
    from app.core.security import decrypt_token
    from app.ingestion.gmail_client import GmailClient
    from app.repositories.user_repo import MailboxRepository

    cutoff = datetime.now(tz=timezone.utc) + _WATCH_RENEWAL_HORIZON

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MailboxConnection)
            .where(MailboxConnection.status == MailboxStatus.active)
            .where(
                or_(
                    MailboxConnection.watch_expiry.is_(None),
                    MailboxConnection.watch_expiry < cutoff,
                )
            )
        )
        connections = result.scalars().all()

    logger.info("watch_renewal_start", count=len(connections))

    for conn in connections:
        conn_id = str(conn.id)
        try:
            from sqlalchemy.orm import selectinload
            # Re-fetch with user eagerly loaded; outer session is already closed.
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(MailboxConnection)
                    .options(selectinload(MailboxConnection.user))
                    .where(MailboxConnection.id == conn.id)
                )
                fresh_conn = result.scalar_one_or_none()
                if fresh_conn is None or not fresh_conn.user.google_refresh_token:
                    logger.warning(
                        "watch_renewal_skip_no_token",
                        connection_id=conn_id,
                        gmail_address=conn.gmail_address,
                    )
                    continue

                refresh_token = decrypt_token(fresh_conn.user.google_refresh_token)
                topic = settings.pubsub_topic

                def _sync_watch(rt: str, tp: str) -> dict:
                    client = GmailClient(rt)
                    return client.setup_watch(tp)

                loop = asyncio.get_running_loop()
                watch_response = await loop.run_in_executor(
                    None, functools.partial(_sync_watch, refresh_token, topic)
                )
                expiry_dt = datetime.fromtimestamp(
                    int(watch_response["expiration"]) / 1000, tz=timezone.utc
                )

                mailbox_repo = MailboxRepository(db)
                await mailbox_repo.update_watch_expiry(fresh_conn, expiry_dt)

            logger.info(
                "watch_renewal_ok",
                connection_id=conn_id,
                gmail_address=conn.gmail_address,
                expiry=expiry_dt.isoformat(),
            )
        except Exception as exc:
            logger.error(
                "watch_renewal_failed",
                connection_id=conn_id,
                gmail_address=conn.gmail_address,
                error=str(exc),
            )


async def _watch_renewal_loop() -> None:
    """Background task: re-run watch renewal every 6 hours."""
    while True:
        await asyncio.sleep(_WATCH_RENEWAL_INTERVAL_SECONDS)
        await _renew_expiring_watches()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup/shutdown tasks.

    Startup:
    - Initialize database tables.
    - Renew any expired/expiring Gmail push watches.
    - Start background task that repeats watch renewal every 6 hours.

    Shutdown:
    - Graceful cleanup.
    """
    await init_db()
    logger.info("database_initialized")

    await _renew_expiring_watches()

    renewal_task = asyncio.create_task(_watch_renewal_loop())

    yield

    renewal_task.cancel()
    try:
        await renewal_task
    except asyncio.CancelledError:
        pass
    logger.info("shutting_down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Inbox Chief of Staff API",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    """Emit a structured log line for every request/response."""
    import time

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(PolicyViolationError)
async def policy_violation_handler(request: Request, exc: PolicyViolationError):
    """Return 403 for any action blocked by the policy guard."""
    logger.warning(
        "policy_violation",
        path=request.url.path,
        detail=str(exc),
    )
    return JSONResponse(
        status_code=403,
        content={"error": "policy_violation", "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(messages.router, prefix="/messages", tags=["messages"])
app.include_router(drafts.router, prefix="/drafts", tags=["drafts"])
app.include_router(briefs.router, prefix="/briefs", tags=["briefs"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(worker.router, prefix="/worker", tags=["worker"])

if settings.node_env == "development":
    from app.api.routes import dev as dev_routes
    app.include_router(dev_routes.router, prefix="/dev", tags=["dev"])
