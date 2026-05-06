"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

# Load .env into os.environ early so libs like requests_oauthlib see the flags.
from dotenv import load_dotenv
load_dotenv()

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import init_db
from app.api.routes import auth, messages, drafts, briefs, webhooks, health, feedback
from app.policy.action_policy import PolicyViolationError

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup/shutdown tasks.

    Startup:
    - Initialize database tables.
    - (TODO) Set up Gmail Pub/Sub watch for connected mailboxes.

    Shutdown:
    - Graceful cleanup.
    """
    await init_db()
    logger.info("database_initialized")

    # TODO: ICE-P1-INIT-01 — iterate MailboxConnections and call GmailClient.setup_watch
    #       for any active connection whose watch_expiry is None or near-expired.

    yield

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
    allow_origins=[settings.app_base_url],
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

if settings.node_env == "development":
    from app.api.routes import dev as dev_routes
    app.include_router(dev_routes.router, prefix="/dev", tags=["dev"])
