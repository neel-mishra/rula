"""Pydantic request/response schemas for drafts."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.draft import DraftStatus


class DraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_run_id: uuid.UUID
    gmail_draft_id: str | None
    body: str
    subject_line: str
    confidence: float
    status: DraftStatus
    user_feedback: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ListDraftsResponse(BaseModel):
    items: list[DraftResponse]
    total: int
    page: int
    page_size: int


class ApproveDraftRequest(BaseModel):
    """Accept the draft as-is (user may optionally provide edited body)."""

    edited_body: str | None = None
    """If provided, replace the draft body before marking accepted."""


class RejectDraftRequest(BaseModel):
    """Reject the draft with an optional reason."""

    feedback: str | None = None


class UpdateDraftRequest(BaseModel):
    """Generic PATCH body — supply only fields being changed."""

    body: str | None = None
    subject_line: str | None = None
    status: DraftStatus | None = None
    user_feedback: str | None = None
