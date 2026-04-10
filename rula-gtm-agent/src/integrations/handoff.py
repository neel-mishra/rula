"""Handoff orchestrator — one-action handoff that routes bulk results to
sequencer, CRM, and review queue stubs in a single call."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import load_config
from src.integrations.connector_policy import HANDOFF_PROSPECTING, get_connector_policy
from src.orchestrator.bulk_prospecting import AuditOutcome, BulkRowResult, BulkRunSummary
from src.safety.atomic_io import atomic_write_json
from src.telemetry.events import TelemetryEvent, emit

logger = __import__("logging").getLogger(__name__)


@dataclass
class SequencerPayload:
    account_id: int
    contact_name: str
    contact_title: str
    email_subject: str
    email_body: str
    email_cta: str
    personalization_model: str = "deterministic"
    personalization_context_source: str = "test_enriched"
    personalization_status: str = "personalized"


@dataclass
class CrmManifestRow:
    account_id: int
    company: str
    industry: str
    top_value_prop: str
    quality_score: float
    human_review_needed: bool
    correlation_id: str = ""
    prospecting_run_id: str = ""


@dataclass
class ReviewQueueEntry:
    account_id: int
    company: str
    reason: str
    error: str | None = None


@dataclass
class HandoffResult:
    run_id: str
    timestamp: str
    sequencer_payloads: list[SequencerPayload] = field(default_factory=list)
    crm_manifest: list[CrmManifestRow] = field(default_factory=list)
    review_queue: list[ReviewQueueEntry] = field(default_factory=list)
    archive_path: str = ""


def _row_to_sequencer(row: BulkRowResult) -> SequencerPayload:
    out = row.output
    assert out is not None
    contact = row.account_payload.get("contact", {})
    return SequencerPayload(
        account_id=row.account_id,
        contact_name=contact.get("name") or "",
        contact_title=contact.get("title") or "",
        email_subject=out.email.subject_line,
        email_body=out.email.body,
        email_cta=out.email.cta,
    )


def _row_to_crm(row: BulkRowResult) -> CrmManifestRow:
    out = row.output
    assert out is not None
    vps = out.matched_value_props
    return CrmManifestRow(
        account_id=row.account_id,
        company=row.account_payload.get("company", ""),
        industry=row.account_payload.get("industry", ""),
        top_value_prop=vps[0].value_prop if vps else "",
        quality_score=out.quality_score,
        human_review_needed=out.human_review_needed,
        correlation_id=out.correlation_id or "",
        prospecting_run_id=out.prospecting_run_id or "",
    )


def _row_to_review(row: BulkRowResult) -> ReviewQueueEntry:
    reason = "audit_review" if row.outcome == AuditOutcome.REVIEW else "pipeline_error"
    return ReviewQueueEntry(
        account_id=row.account_id,
        company=row.account_payload.get("company", ""),
        reason=reason,
        error=row.error,
    )


def _write_json(path: Path, data: Any) -> None:
    atomic_write_json(path, data)


def _write_archive(summary: BulkRunSummary, result: HandoffResult, base_dir: Path) -> str:
    """Write a durable run archive containing all drafts and metadata."""
    run_dir = base_dir / summary.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ctx_archive: dict[str, str] = {}
    try:
        from src.context.business_context import BusinessContextRegistry
        ctx_archive = BusinessContextRegistry.get().telemetry_metadata()
    except Exception:
        pass

    manifest = {
        "export_contract_version": "1",
        "run_id": summary.run_id,
        "timestamp": result.timestamp,
        "source": summary.source,
        "total": summary.total,
        "passed": summary.passed,
        "review": summary.review,
        "errors": summary.errors,
        "policy_skipped": getattr(summary, "policy_skipped", 0),
        "queue_mode": getattr(summary, "queue_mode", "file_order"),
        "duration_ms": summary.duration_ms,
        **ctx_archive,
    }
    _write_json(run_dir / "manifest.json", manifest)

    seq_dir = run_dir / "sequencer_payloads"
    for sp in result.sequencer_payloads:
        _write_json(seq_dir / f"{sp.account_id}.json", asdict(sp))

    crm_dir = run_dir / "crm_manifest"
    _write_json(crm_dir / "manifest.json", [asdict(r) for r in result.crm_manifest])

    review_dir = run_dir / "review_queue"
    for rq in result.review_queue:
        _write_json(review_dir / f"{rq.account_id}.json", asdict(rq))

    return str(run_dir)


def handoff_orchestrator(summary: BulkRunSummary) -> HandoffResult:
    """Execute the one-click orchestrated handoff.

    Passes go to sequencer + CRM stubs; failures go to review queue.
    An archive of the full run is written automatically.
    """
    cfg = load_config()
    ts = datetime.now(timezone.utc).isoformat()

    ctx_meta: dict[str, str] = {}
    if cfg.business_dna_enabled:
        try:
            from src.context.business_context import BusinessContextRegistry
            ctx_meta = BusinessContextRegistry.get().telemetry_metadata()
        except Exception:
            ctx_meta = {"context_loaded": "False"}

    seq_payloads = [_row_to_sequencer(r) for r in summary.pass_rows]
    crm_rows = [_row_to_crm(r) for r in summary.pass_rows]
    review_entries = [_row_to_review(r) for r in summary.review_rows + summary.error_rows]

    result = HandoffResult(
        run_id=summary.run_id,
        timestamp=ts,
        sequencer_payloads=seq_payloads,
        crm_manifest=crm_rows,
        review_queue=review_entries,
    )

    # Write review queue entries
    review_dir = Path(cfg.human_review_dir)
    for entry in review_entries:
        _write_json(review_dir / f"{summary.run_id}_{entry.account_id}.json", asdict(entry))

    # Write durable archive
    archive_dir = Path(cfg.run_archive_dir)
    result.archive_path = _write_archive(summary, result, archive_dir)

    _hpol = get_connector_policy(HANDOFF_PROSPECTING)
    emit(TelemetryEvent(
        event_type="handoff_orchestrated",
        pipeline="prospecting",
        metadata={
            "run_id": summary.run_id,
            "sequencer_count": str(len(seq_payloads)),
            "crm_count": str(len(crm_rows)),
            "review_count": str(len(review_entries)),
            "connector_policy_timeout_s": str(_hpol.timeout_seconds),
            "connector_policy_retries": str(_hpol.max_retries),
            "connector_idempotency": _hpol.idempotency_scope,
            **ctx_meta,
        },
    ))
    for _ in seq_payloads:
        emit(TelemetryEvent(
            event_type="handoff_destination_sequencer",
            pipeline="prospecting",
            metadata={"run_id": summary.run_id},
        ))
    for _ in crm_rows:
        emit(TelemetryEvent(
            event_type="handoff_destination_crm",
            pipeline="prospecting",
            metadata={"run_id": summary.run_id},
        ))
    for _ in review_entries:
        emit(TelemetryEvent(
            event_type="handoff_destination_review_queue",
            pipeline="prospecting",
            metadata={"run_id": summary.run_id},
        ))

    return result
