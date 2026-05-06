"""Dev-only routes — only registered when NODE_ENV=development."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.ingestion.webhook_handler import handle_new_message
from app.repositories.user_repo import UserRepository

logger = structlog.get_logger(__name__)

router = APIRouter()


class IngestRequest(BaseModel):
    gmail_message_id: str
    user_email: str


@router.post("/ingest")
async def dev_ingest(
    body: IngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Simulate a Gmail Pub/Sub ingestion event without a real webhook.

    Looks up the user by email, then runs the full ingestion pipeline for the
    given Gmail message ID.  Intended for local development only — this route
    is not registered in staging or production.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(body.user_email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"No user found with email {body.user_email!r}. "
                   "Have you completed the OAuth flow at /auth/login?",
        )

    logger.info(
        "dev_ingest_triggered",
        gmail_message_id=body.gmail_message_id,
        user_email=body.user_email,
        user_id=str(user.id),
    )

    await handle_new_message(
        gmail_message_id=body.gmail_message_id,
        user_id=str(user.id),
        db=db,
    )

    return {
        "status": "ok",
        "gmail_message_id": body.gmail_message_id,
        "user_email": body.user_email,
    }
