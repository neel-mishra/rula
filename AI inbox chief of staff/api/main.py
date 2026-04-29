"""
FastAPI application entrypoint.
- OAuth callbacks, Gmail webhooks, assistant interface, health checks.
- No auto-send paths. No gmail.send scope.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.db import dispose_db, init_db
from core.observability.tracing import init_tracing

log = structlog.get_logger(__name__)

# Initialize tracing before FastAPI is constructed so the auto-instrumentor
# wraps this app's instance. No-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
init_tracing("inbox-cos-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup.begin", env=settings.app_env)
    await init_db()
    log.info("startup.db_ready")
    yield
    # Graceful shutdown
    from core.security.csrf import close_redis
    await close_redis()
    await dispose_db()
    log.info("shutdown.complete")


app = FastAPI(
    title="AI Inbox Chief of Staff",
    version="0.1.0",
    description="Production-grade AI inbox management — Gmail integration, triage, drafts, briefs.",
    lifespan=lifespan,
    # Disable docs in production
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# CORS — split-host (Vercel + Render): set CORS_ALLOWED_ORIGINS on the API.
# Dev always includes http://localhost:3000. Optional CORS_ALLOW_VERCEL_PREVIEW=true
# for https://*.vercel.app preview deployments.
_cors_origins = settings.cors_origins_list()
_cors_regex = settings.cors_origin_regex()
if settings.app_env in ("staging", "prod") and not _cors_origins and not _cors_regex:
    log.warning(
        "cors.not_configured",
        app_env=settings.app_env,
        hint="Set CORS_ALLOWED_ORIGINS and/or CORS_ALLOW_VERCEL_PREVIEW for browser clients.",
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routers
from api.routers import (  # noqa: E402
    activity,
    admin,
    assistant,
    auth,
    briefs,
    data_export,
    experiments,
    feedback,
    gold_eval,
    health,
    mailbox_connect,
    mailboxes,
    memories,
    slo,
    undo,
    webhooks,
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(mailbox_connect.router, prefix="/mailbox-connect", tags=["mailbox-connect"])
app.include_router(mailboxes.router, prefix="/mailboxes", tags=["mailboxes"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(assistant.router, prefix="/assistant", tags=["assistant"])
app.include_router(undo.router, prefix="/undo", tags=["undo"])
app.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
app.include_router(data_export.router, prefix="/data", tags=["data"])
app.include_router(activity.router, prefix="/activity", tags=["activity"])
app.include_router(briefs.router, prefix="/briefs", tags=["briefs"])
app.include_router(memories.router, prefix="/memories", tags=["memories"])
app.include_router(experiments.router, prefix="/experiments", tags=["experiments"])
app.include_router(slo.router, prefix="/slo", tags=["slo"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(gold_eval.router, prefix="/admin/gold-eval", tags=["admin", "gold-eval"])
