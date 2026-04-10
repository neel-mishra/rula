"""Tests for MAP handoff orchestrator.

Validates CRM manifest, review queue, and archive writes.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


from src.integrations.map_handoff import (
    MapHandoffResult,
    map_handoff_orchestrator,
)
from src.orchestrator.bulk_map import (
    BulkMapRow,
    BulkMapSummary,
    MapOutcome,
    run_map_verification_bulk,
)


def _load_evidence() -> list[dict]:
    return json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))


def _build_test_summary() -> BulkMapSummary:
    items = _load_evidence()
    return run_map_verification_bulk(items, actor_role="admin")


def test_handoff_returns_result():
    summary = _build_test_summary()
    result = map_handoff_orchestrator(summary)
    assert isinstance(result, MapHandoffResult)
    assert result.run_id == summary.run_id


def test_handoff_crm_manifest_for_pass_rows():
    summary = _build_test_summary()
    result = map_handoff_orchestrator(summary)
    assert len(result.crm_manifest) == summary.passed
    for row in result.crm_manifest:
        assert row.evidence_id
        assert row.confidence_tier in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(row.recommended_actions, list)


def test_handoff_review_queue_for_non_pass_rows():
    summary = _build_test_summary()
    result = map_handoff_orchestrator(summary)
    expected_review_count = summary.review + summary.errors
    assert len(result.review_queue) == expected_review_count


def test_handoff_writes_archive():
    summary = _build_test_summary()
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.integrations.map_handoff.load_config") as mock_cfg:
            cfg = mock_cfg.return_value
            cfg.human_review_dir = str(Path(tmpdir) / "review")
            cfg.run_archive_dir = str(Path(tmpdir) / "archive")
            result = map_handoff_orchestrator(summary)
        assert result.archive_path
        archive_dir = Path(result.archive_path)
        assert archive_dir.exists()
        manifest_path = archive_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_id"] == summary.run_id
        assert manifest["total"] == summary.total
        crm_manifest_path = archive_dir / "crm_manifest" / "manifest.json"
        crm_rows = json.loads(crm_manifest_path.read_text())
        assert crm_rows
        assert "recommended_actions" in crm_rows[0]


def test_handoff_no_sequencer_payloads():
    """MAP handoff should never include sequencer payloads."""
    summary = _build_test_summary()
    result = map_handoff_orchestrator(summary)
    assert not hasattr(result, "sequencer_payloads")


def test_handoff_malicious_evidence_id_writes_safe_filename():
    """R-001: review queue files must not embed raw path segments in filenames."""
    summary = BulkMapSummary(
        run_id="00000000-0000-0000-0000-000000000001",
        total=1,
        passed=0,
        review=0,
        errors=1,
        duration_ms=0.0,
        rows=[
            BulkMapRow(
                evidence_id="../../evil",
                evidence_payload={},
                outcome=MapOutcome.ERROR,
                output=None,
                error="synthetic",
            ),
        ],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("src.integrations.map_handoff.load_config") as mock_cfg:
            cfg = mock_cfg.return_value
            cfg.human_review_dir = str(Path(tmpdir) / "review")
            cfg.run_archive_dir = str(Path(tmpdir) / "archive")
            map_handoff_orchestrator(summary)
        review_root = Path(tmpdir) / "review"
        names = list(review_root.glob("*.json"))
        assert len(names) == 1
        assert ".." not in names[0].name
        assert "/" not in names[0].name
        payload = json.loads(names[0].read_text(encoding="utf-8"))
        assert payload["evidence_id"] == "../../evil"
