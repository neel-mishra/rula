"""MAP handoff orchestrator — CRM manifest + review queue + optional archive."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import load_config
from src.integrations.connector_policy import HANDOFF_MAP, get_connector_policy
from src.orchestrator.bulk_map import BulkMapRow, BulkMapSummary, MapOutcome
from src.safety.atomic_io import atomic_write_json
from src.safety.paths import safe_handoff_filename_component
from src.telemetry.events import TelemetryEvent, emit


@dataclass
class MapCrmManifestRow:
    evidence_id: str
    confidence_tier: str
    confidence_score: int
    risk_factors: list[str]
    audit_pass: bool | None
    scoring_version: str
    recommended_actions: list[str] = field(default_factory=list)
    map_run_id: str = ""
    correlation_id: str = ""
    prospecting_run_id: str = ""
    account_id: int | None = None


@dataclass
class MapReviewQueueEntry:
    evidence_id: str
    reason: str
    confidence_tier: str
    error: str | None = None


@dataclass
class MapHandoffResult:
    run_id: str
    timestamp: str
    crm_manifest: list[MapCrmManifestRow] = field(default_factory=list)
    review_queue: list[MapReviewQueueEntry] = field(default_factory=list)
    archive_path: str = ""


def _row_to_crm(row: BulkMapRow) -> MapCrmManifestRow:
    out = row.output
    assert out is not None
    return MapCrmManifestRow(
        evidence_id=row.evidence_id,
        confidence_tier=out.confidence_tier,
        confidence_score=out.confidence_score,
        risk_factors=out.risk_factors,
        audit_pass=out.judge_pass,
        scoring_version=out.scoring_version or "",
        recommended_actions=list(out.recommended_actions or []),
        map_run_id=out.map_run_id or "",
        correlation_id=out.correlation_id or "",
        prospecting_run_id=out.prospecting_run_id or "",
        account_id=out.account_id,
    )


def _row_to_review(row: BulkMapRow) -> MapReviewQueueEntry:
    reason = "low_confidence" if row.output and row.output.confidence_tier == "LOW" else "audit_fail"
    if row.outcome == MapOutcome.ERROR:
        reason = "pipeline_error"
    return MapReviewQueueEntry(
        evidence_id=row.evidence_id,
        reason=reason,
        confidence_tier=row.output.confidence_tier if row.output else "UNKNOWN",
        error=row.error,
    )


def _write_json(path: Path, data: Any, *, base_dir: Path | None = None) -> None:
    atomic_write_json(path, data, base_dir=base_dir)


def _write_map_archive(summary: BulkMapSummary, result: MapHandoffResult, base_dir: Path) -> str:
    run_id_safe = safe_handoff_filename_component(summary.run_id)
    run_dir = base_dir / f"map_{run_id_safe}"
    run_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "export_contract_version": "1",
        "run_id": summary.run_id,
        "timestamp": result.timestamp,
        "total": summary.total,
        "passed": summary.passed,
        "review": summary.review,
        "errors": summary.errors,
        "duration_ms": summary.duration_ms,
    }
    _write_json(run_dir / "manifest.json", manifest, base_dir=run_dir)

    crm_dir = run_dir / "crm_manifest"
    _write_json(crm_dir / "manifest.json", [asdict(r) for r in result.crm_manifest], base_dir=run_dir)

    review_dir = run_dir / "review_queue"
    for rq in result.review_queue:
        safe_eid = safe_handoff_filename_component(rq.evidence_id)
        _write_json(
            review_dir / f"{safe_eid}.json",
            asdict(rq),
            base_dir=review_dir,
        )

    return str(run_dir)


def map_handoff_orchestrator(summary: BulkMapSummary) -> MapHandoffResult:
    """One-action MAP handoff: CRM + review queue + archive."""
    cfg = load_config()
    ts = datetime.now(timezone.utc).isoformat()

    crm_rows = [_row_to_crm(r) for r in summary.pass_rows]
    review_entries = [_row_to_review(r) for r in summary.review_rows + summary.error_rows]

    result = MapHandoffResult(
        run_id=summary.run_id,
        timestamp=ts,
        crm_manifest=crm_rows,
        review_queue=review_entries,
    )

    review_dir = Path(cfg.human_review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    run_id_safe = safe_handoff_filename_component(summary.run_id)
    for entry in review_entries:
        safe_eid = safe_handoff_filename_component(entry.evidence_id)
        out_path = review_dir / f"map_{run_id_safe}_{safe_eid}.json"
        _write_json(out_path, asdict(entry), base_dir=review_dir)

    archive_dir = Path(cfg.run_archive_dir)
    result.archive_path = _write_map_archive(summary, result, archive_dir)

    _mpol = get_connector_policy(HANDOFF_MAP)
    emit(TelemetryEvent(
        event_type="map_handoff_orchestrated",
        pipeline="map_verification",
        metadata={
            "run_id": summary.run_id,
            "crm_count": str(len(crm_rows)),
            "review_count": str(len(review_entries)),
            "connector_policy_timeout_s": str(_mpol.timeout_seconds),
            "connector_policy_retries": str(_mpol.max_retries),
            "connector_idempotency": _mpol.idempotency_scope,
        },
    ))
    for _ in crm_rows:
        emit(TelemetryEvent(
            event_type="handoff_destination_crm",
            pipeline="map_verification",
            metadata={"run_id": summary.run_id},
        ))
    for _ in review_entries:
        emit(TelemetryEvent(
            event_type="handoff_destination_review_queue",
            pipeline="map_verification",
            metadata={"run_id": summary.run_id},
        ))

    return result
