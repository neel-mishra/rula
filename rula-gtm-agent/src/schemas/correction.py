from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class CorrectionEvent(BaseModel):
    """Records a single correction (system auto-retry or AE in-app edit)."""

    correction_id: str
    account_id: int
    field_edited: str
    before: str
    after: str
    edited_by: str = "ae"
    edited_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""
    correction_type: str = "ae_edit"
    reaudit_status: str = "pending"
