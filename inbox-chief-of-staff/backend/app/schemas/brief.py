"""Pydantic request/response schemas for briefs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.brief import TimeWindow


class BriefResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    time_window: TimeWindow
    summary_markdown: str
    action_items: list[str]
    message_ids: list[str]
    created_at: datetime


class ListBriefsResponse(BaseModel):
    items: list[BriefResponse]
    total: int
