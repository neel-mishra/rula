"""Tests for bulk MAP verification runner.

Validates continue-on-error semantics and classification stability.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from src.orchestrator.bulk_map import (
    BulkMapSummary,
    run_map_verification_bulk,
)


def _load_evidence() -> list[dict]:
    return json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))


def test_bulk_run_classifies_all_evidence():
    items = _load_evidence()
    summary = run_map_verification_bulk(items, actor_role="admin")
    assert isinstance(summary, BulkMapSummary)
    assert summary.total == len(items)
    assert summary.passed + summary.review + summary.errors == summary.total
    assert summary.errors == 0


def test_bulk_run_golden_tiers():
    items = _load_evidence()
    summary = run_map_verification_bulk(items, actor_role="admin")
    tier_map = {r.evidence_id: r.output.confidence_tier for r in summary.rows if r.output}
    assert tier_map["A"] == "HIGH"
    assert tier_map["B"] == "LOW"
    assert tier_map["C"] == "MEDIUM"


def test_bulk_run_continue_on_error():
    """Inject a failing row and verify the batch continues."""
    items = _load_evidence()
    bad_item = {"evidence_id": "FAIL", "text": ""}
    items_with_failure = items + [bad_item]

    with patch("src.orchestrator.bulk_map.run_map_verification", side_effect=_mock_with_error):
        summary = run_map_verification_bulk(items_with_failure, actor_role="admin")

    assert summary.total == len(items_with_failure)
    assert summary.errors == 1
    assert summary.error_rows[0].evidence_id == "FAIL"
    assert len(summary.pass_rows) + len(summary.review_rows) == len(items)


def _mock_with_error(eid, text, *, actor_role="system", enable_audit=True):
    if eid == "FAIL":
        raise RuntimeError("Injected test failure")
    from src.orchestrator.graph import run_map_verification
    return run_map_verification(eid, text, actor_role=actor_role)


def test_bulk_summary_properties():
    items = _load_evidence()
    summary = run_map_verification_bulk(items, actor_role="admin")
    assert len(summary.pass_rows) == summary.passed
    assert len(summary.review_rows) == summary.review
    assert len(summary.error_rows) == summary.errors
    assert summary.duration_ms > 0
    assert summary.run_id


def test_bulk_rows_have_parse_summary():
    """Verify that VerificationOutput includes parse_summary from the pipeline."""
    items = _load_evidence()
    summary = run_map_verification_bulk(items, actor_role="admin")
    for row in summary.rows:
        if row.output:
            assert row.output.parse_summary is not None, f"Missing parse_summary for {row.evidence_id}"
            assert row.output.score_breakdown is not None, f"Missing score_breakdown for {row.evidence_id}"
