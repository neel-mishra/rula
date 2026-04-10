from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.config import load_config
from src.orchestrator.graph import run_prospecting
from src.schemas.prospecting import ProspectingOutput
from src.telemetry.events import TelemetryEvent, emit


class AuditOutcome:
    PASS = "audit_pass"
    REVIEW = "needs_review"
    ERROR = "pipeline_error"
    POLICY_SKIP = "policy_skip"


@dataclass
class BulkRowResult:
    account_id: int
    account_payload: dict[str, Any]
    outcome: str
    output: ProspectingOutput | None = None
    error: str | None = None


@dataclass
class BulkRunSummary:
    run_id: str
    source: str
    total: int
    passed: int
    review: int
    errors: int
    policy_skipped: int
    duration_ms: float
    queue_mode: str = "file_order"
    rows: list[BulkRowResult] = field(default_factory=list)

    @property
    def pass_rows(self) -> list[BulkRowResult]:
        return [r for r in self.rows if r.outcome == AuditOutcome.PASS]

    @property
    def review_rows(self) -> list[BulkRowResult]:
        return [r for r in self.rows if r.outcome == AuditOutcome.REVIEW]

    @property
    def error_rows(self) -> list[BulkRowResult]:
        return [r for r in self.rows if r.outcome == AuditOutcome.ERROR]

    @property
    def policy_skip_rows(self) -> list[BulkRowResult]:
        return [r for r in self.rows if r.outcome == AuditOutcome.POLICY_SKIP]


def run_prospecting_bulk(
    accounts: list[dict[str, Any]],
    *,
    actor_role: str = "ae",
    source: str = "test_data",
    queue_mode: str | None = None,
) -> BulkRunSummary:
    """Run the prospecting pipeline for every account in the list.

    Returns a BulkRunSummary with per-row outcomes classified as
    audit_pass, needs_review, or pipeline_error.
    """
    cfg = load_config()
    qm = queue_mode if queue_mode is not None else cfg.bulk_default_queue
    if qm not in ("file_order", "heuristic"):
        qm = "file_order"

    accounts_to_run = list(accounts)
    if qm == "heuristic":
        from src.agents.prospecting.queue import sort_accounts_by_heuristic

        accounts_to_run = sort_accounts_by_heuristic(accounts_to_run)

    run_id = str(uuid.uuid4())
    t0 = time.monotonic()
    rows: list[BulkRowResult] = []

    for acct in accounts_to_run:
        aid = acct.get("account_id", 0)
        try:
            output = run_prospecting(acct, actor_role=actor_role)
            if getattr(output, "skipped", False):
                rows.append(
                    BulkRowResult(
                        account_id=aid,
                        account_payload=acct,
                        outcome=AuditOutcome.POLICY_SKIP,
                        output=output,
                    )
                )
                continue
            if output.judge_pass:
                outcome = AuditOutcome.PASS
            else:
                outcome = AuditOutcome.REVIEW
            rows.append(BulkRowResult(
                account_id=aid,
                account_payload=acct,
                outcome=outcome,
                output=output,
            ))
        except Exception as exc:
            rows.append(BulkRowResult(
                account_id=aid,
                account_payload=acct,
                outcome=AuditOutcome.ERROR,
                error=str(exc),
            ))

    elapsed = (time.monotonic() - t0) * 1000
    summary = BulkRunSummary(
        run_id=run_id,
        source=source,
        total=len(accounts_to_run),
        passed=sum(1 for r in rows if r.outcome == AuditOutcome.PASS),
        review=sum(1 for r in rows if r.outcome == AuditOutcome.REVIEW),
        errors=sum(1 for r in rows if r.outcome == AuditOutcome.ERROR),
        policy_skipped=sum(1 for r in rows if r.outcome == AuditOutcome.POLICY_SKIP),
        duration_ms=elapsed,
        queue_mode=qm,
        rows=rows,
    )

    emit(TelemetryEvent(
        event_type="bulk_pipeline_complete",
        pipeline="prospecting",
        duration_ms=elapsed,
        success=summary.errors == 0,
        metadata={
            "run_id": run_id,
            "source": source,
            "total": str(summary.total),
            "passed": str(summary.passed),
            "review": str(summary.review),
            "errors": str(summary.errors),
            "policy_skipped": str(summary.policy_skipped),
            "bulk_queue_mode": qm,
        },
    ))

    return summary
