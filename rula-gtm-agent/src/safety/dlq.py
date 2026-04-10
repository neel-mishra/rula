from __future__ import annotations

import json
import traceback
from datetime import datetime, UTC
from pathlib import Path

from src.safety.incidents import create_incident
from src.safety.sanitize import redact_context_for_persistence

DLQ_PATH = Path("out/dlq.jsonl")


def log_failure(
    *,
    pipeline: str,
    error: BaseException,
    context: dict,
) -> None:
    DLQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    safe_ctx = redact_context_for_persistence(context)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "pipeline": pipeline,
        "error": repr(error),
        "traceback": traceback.format_exc(),
        "context": safe_ctx,
    }
    with DLQ_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    err_name = error.__class__.__name__
    severity = "high" if err_name in {"PermissionError", "RuntimeError"} else "medium"
    create_incident(
        pipeline=pipeline,
        severity=severity,
        summary=f"{pipeline} failure: {err_name}",
        context=safe_ctx,
    )
