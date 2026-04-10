from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.safety.sanitize import redact_context_for_persistence

INCIDENTS_PATH = Path("out/incidents.jsonl")


def create_incident(*, pipeline: str, severity: str, summary: str, context: dict) -> None:
    INCIDENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe_ctx = redact_context_for_persistence(context)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "pipeline": pipeline,
        "severity": severity,
        "summary": summary,
        "context": safe_ctx,
    }
    with INCIDENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
