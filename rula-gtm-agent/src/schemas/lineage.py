from __future__ import annotations

from datetime import datetime, UTC
from pydantic import BaseModel


class LineageRecord(BaseModel):
    trace_id: str
    step: str
    timestamp: str
    details: dict

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()
