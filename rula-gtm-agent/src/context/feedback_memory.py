from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

MEMORY_PATH = Path("out/feedback_memory.jsonl")


def append_entry(
    *,
    trace_id: str,
    pipeline: str,
    judge_pass: bool,
    audit_score: float,
    correction_attempts: int,
    reasoning: str,
    extra: dict | None = None,
) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "trace_id": trace_id,
        "pipeline": pipeline,
        "judge_pass": judge_pass,
        "audit_score": audit_score,
        "correction_attempts": correction_attempts,
        "reasoning": reasoning,
        "extra": extra or {},
    }
    with MEMORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
