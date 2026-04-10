"""Bulk MAP verification runner — continue-on-error semantics."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.orchestrator.graph import run_map_verification
from src.schemas.map_verification import VerificationOutput
from src.telemetry.events import TelemetryEvent, emit


class MapOutcome:
    PASS = "audit_pass"
    REVIEW = "needs_review"
    ERROR = "pipeline_error"


@dataclass
class BulkMapRow:
    evidence_id: str
    evidence_payload: dict[str, Any]
    outcome: str
    output: VerificationOutput | None = None
    error: str | None = None


@dataclass
class BulkMapSummary:
    run_id: str
    total: int
    passed: int
    review: int
    errors: int
    duration_ms: float
    rows: list[BulkMapRow] = field(default_factory=list)

    @property
    def pass_rows(self) -> list[BulkMapRow]:
        return [r for r in self.rows if r.outcome == MapOutcome.PASS]

    @property
    def review_rows(self) -> list[BulkMapRow]:
        return [r for r in self.rows if r.outcome == MapOutcome.REVIEW]

    @property
    def error_rows(self) -> list[BulkMapRow]:
        return [r for r in self.rows if r.outcome == MapOutcome.ERROR]


def run_map_verification_bulk(
    evidence_items: list[dict[str, Any]],
    *,
    actor_role: str = "user",
) -> BulkMapSummary:
    run_id = str(uuid.uuid4())
    t0 = time.monotonic()
    rows: list[BulkMapRow] = []

    for item in evidence_items:
        eid = item.get("evidence_id", "?")
        text = item.get("text", "")
        try:
            output = run_map_verification(eid, text, actor_role=actor_role)
            if output.judge_pass:
                outcome = MapOutcome.PASS
            elif output.confidence_tier == "LOW":
                outcome = MapOutcome.REVIEW
            else:
                outcome = MapOutcome.REVIEW if not output.judge_pass else MapOutcome.PASS
            rows.append(BulkMapRow(
                evidence_id=eid,
                evidence_payload=item,
                outcome=outcome,
                output=output,
            ))
        except Exception as exc:
            rows.append(BulkMapRow(
                evidence_id=eid,
                evidence_payload=item,
                outcome=MapOutcome.ERROR,
                error=str(exc),
            ))

    elapsed = (time.monotonic() - t0) * 1000
    summary = BulkMapSummary(
        run_id=run_id,
        total=len(evidence_items),
        passed=sum(1 for r in rows if r.outcome == MapOutcome.PASS),
        review=sum(1 for r in rows if r.outcome == MapOutcome.REVIEW),
        errors=sum(1 for r in rows if r.outcome == MapOutcome.ERROR),
        duration_ms=elapsed,
        rows=rows,
    )

    emit(TelemetryEvent(
        event_type="bulk_pipeline_complete",
        pipeline="map_verification",
        duration_ms=elapsed,
        success=summary.errors == 0,
        metadata={
            "run_id": run_id,
            "total": str(summary.total),
            "passed": str(summary.passed),
            "review": str(summary.review),
            "errors": str(summary.errors),
        },
    ))

    return summary
