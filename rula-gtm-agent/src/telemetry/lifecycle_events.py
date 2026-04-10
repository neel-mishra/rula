"""Normalized lifecycle domain events (shared IDs for trace reconstruction)."""
from __future__ import annotations

from src.telemetry.events import TelemetryEvent, emit

# Event names (stable contract for operators / replay).
ACCOUNT_ASSIGNED = "account_assigned"
OUTREACH_GENERATED = "outreach_generated"
OUTREACH_SENT = "outreach_sent"
COMMITMENT_EVIDENCE_CAPTURED = "commitment_evidence_captured"
MAP_VERIFICATION_COMPLETED = "map_verification_completed"


def emit_lifecycle(
    lifecycle_event: str,
    *,
    pipeline: str,
    metadata: dict[str, str],
) -> None:
    """Emit a single lifecycle row; values must be non-sensitive strings."""
    meta = {"lifecycle_event": lifecycle_event, **metadata}
    emit(
        TelemetryEvent(
            event_type="lifecycle_domain",
            pipeline=pipeline,
            success=True,
            metadata=meta,
        )
    )
