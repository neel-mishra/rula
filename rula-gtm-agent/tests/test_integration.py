from __future__ import annotations

import json
from pathlib import Path

from src.integrations.export import build_map_export, build_prospecting_export
from src.orchestrator.graph import run_map_verification, run_prospecting


def test_prospecting_export_has_required_fields() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    result = run_prospecting(accounts[0]).model_dump()
    export = build_prospecting_export(result, accounts[0])
    d = export.to_dict()

    assert d["account_id"] == accounts[0]["account_id"]
    assert d["company"] == accounts[0]["company"]
    assert d["email_subject"]
    assert d["email_body"]
    assert d["top_value_prop"]
    assert "content_model" in d
    assert "content_prompt_version" in d
    assert "content_validation_status" in d
    assert "provider_primary" in d
    assert "provider_fallback_used" in d
    assert "confidence_caveats" in d


def test_map_export_has_required_fields() -> None:
    evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    result = run_map_verification(evidence[0]["evidence_id"], evidence[0]["text"]).model_dump()
    export = build_map_export(result, threshold_rationale="test rationale")
    d = export.to_dict()

    assert d["evidence_id"] == evidence[0]["evidence_id"]
    assert d["confidence_tier"] in ("HIGH", "MEDIUM", "LOW")
    assert isinstance(d["confidence_score"], int)
    assert isinstance(d["risk_factors"], list)
    assert isinstance(d["recommended_actions"], list)
    assert d["map_threshold_rationale"] == "test rationale"
    assert "confidence_caveats" in d
    assert d.get("crm_handoff_state") == "simulated"
    assert isinstance(d.get("revops_review_checklist"), list)
    assert d["revops_review_checklist"]


def test_export_to_json_is_valid() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    result = run_prospecting(accounts[0]).model_dump()
    export = build_prospecting_export(result, accounts[0])
    parsed = json.loads(export.to_json())
    assert parsed["account_id"] == accounts[0]["account_id"]


def test_caveats_populated_for_low_confidence() -> None:
    evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    result = run_map_verification(evidence[1]["evidence_id"], evidence[1]["text"]).model_dump()
    export = build_map_export(result)
    if result["confidence_tier"] == "LOW":
        assert any("Low confidence" in c for c in export.confidence_caveats)
