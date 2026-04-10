from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.security.rbac import require_permission


def _parse_ts(row: dict) -> datetime | None:
    raw = row.get("ts") or row.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _prune_jsonl(path: Path, cutoff: datetime) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    lines = path.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    removed = 0
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        ts = _parse_ts(row)
        if ts is not None and ts < cutoff:
            removed += 1
            continue
        kept.append(line)
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return len(lines), removed


def enforce_retention(days: int = 30, actor_role: str = "system") -> dict[str, int]:
    require_permission(actor_role, "retention:run")
    cutoff = datetime.now(UTC) - timedelta(days=days)
    targets = [
        Path("lineage.jsonl"),
        Path("telemetry_events.jsonl"),
        Path("out/feedback_memory.jsonl"),
        Path("out/dlq.jsonl"),
        Path("out/incidents.jsonl"),
    ]
    scanned = 0
    removed = 0
    for path in targets:
        s, r = _prune_jsonl(path, cutoff)
        scanned += s
        removed += r
    return {"days": days, "rows_scanned": scanned, "rows_removed": removed}
