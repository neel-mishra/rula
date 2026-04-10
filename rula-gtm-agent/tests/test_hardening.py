from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.agents.verification.capture import map_capture_to_evidence_text
from src.governance.retention import enforce_retention
from src.orchestrator.graph import run_map_verification
from src.safety.dlq import log_failure
from src.schemas.map_capture import MapCampaignPlan, MapCaptureInput
from src.security.rbac import require_permission


def test_rbac_blocks_viewer_from_running_map() -> None:
    with pytest.raises(PermissionError):
        run_map_verification("X", "Email from VP: we are in for Q2", actor_role="viewer")


def test_rbac_permission_matrix() -> None:
    require_permission("admin", "retention:run")
    with pytest.raises(PermissionError):
        require_permission("user", "retention:run")


def test_retention_prunes_old_rows() -> None:
    out = Path("out")
    out.mkdir(exist_ok=True)
    old = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    fresh = datetime.now(UTC).isoformat()
    p = Path("out/feedback_memory.jsonl")
    p.write_text(
        "\n".join(
            [
                json.dumps({"ts": old, "a": 1}),
                json.dumps({"ts": fresh, "a": 2}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = enforce_retention(30, actor_role="admin")
    assert report["rows_removed"] >= 1
    content = p.read_text(encoding="utf-8")
    assert '"a": 1' not in content
    assert '"a": 2' in content


def test_incident_created_on_dlq_failure() -> None:
    incidents = Path("out/incidents.jsonl")
    before = incidents.read_text(encoding="utf-8").splitlines() if incidents.exists() else []
    err = RuntimeError("boom")
    try:
        raise err
    except RuntimeError as e:
        log_failure(pipeline="prospecting", error=e, context={"unit_test": True})
    after = incidents.read_text(encoding="utf-8").splitlines() if incidents.exists() else []
    assert len(after) >= len(before) + 1


def test_map_capture_redesign_compiles_and_runs() -> None:
    capture = MapCaptureInput(
        evidence_id="CAP1",
        source_type="Email",
        committer_name="Dana",
        committer_title="VP Total Rewards",
        commitment_language="We are excited to move forward.",
        campaign_plan=[MapCampaignPlan(campaign_type="launch_email", quarter="Q2")],
    )
    evidence = map_capture_to_evidence_text(capture)
    out = run_map_verification(capture.evidence_id, evidence, actor_role="user")
    assert out.confidence_tier in {"HIGH", "MEDIUM", "LOW"}
