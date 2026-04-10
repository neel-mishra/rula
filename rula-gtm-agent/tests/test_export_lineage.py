from __future__ import annotations

from unittest.mock import patch

from src.integrations.export import build_map_export, build_prospecting_export
from src.schemas.evidence_artifact import LineageExportBlock


def _cfg(**kwargs):
    from types import SimpleNamespace

    base = dict(
        export_lineage_enabled=True,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_prospecting_export_includes_lineage_when_enabled() -> None:
    result = {
        "account_id": 1,
        "matched_value_props": [{"value_prop": "vp", "score": 80, "reasoning": "r"}],
        "email": {"subject_line": "S", "body": "B", "cta": "C"},
        "discovery_questions": ["Q1?", "Q2?", "Q3?"],
        "quality_score": 4.0,
        "human_review_needed": False,
        "judge_pass": True,
        "judge_audit_score": 4.0,
    }
    account = {"account_id": 1, "company": "Co", "industry": "Health system", "us_employees": 5000}
    lin = LineageExportBlock(correlation_id="corr-1", prospecting_run_id="run-1")
    with patch("src.integrations.export.load_config", return_value=_cfg(export_lineage_enabled=True)):
        ex = build_prospecting_export(result, account, lineage=lin)
    d = ex.to_dict()
    assert d.get("lineage_export") is not None
    assert d["lineage_export"]["correlation_id"] == "corr-1"


def test_prospecting_export_omits_lineage_when_disabled() -> None:
    result = {
        "account_id": 1,
        "matched_value_props": [{"value_prop": "vp", "score": 80, "reasoning": "r"}],
        "email": {"subject_line": "S", "body": "B", "cta": "C"},
        "discovery_questions": ["Q1?", "Q2?", "Q3?"],
        "quality_score": 4.0,
        "human_review_needed": False,
        "judge_pass": True,
        "judge_audit_score": 4.0,
    }
    account = {"account_id": 1, "company": "Co", "industry": "Health system", "us_employees": 5000}
    lin = LineageExportBlock(correlation_id="x")
    with patch("src.integrations.export.load_config", return_value=_cfg(export_lineage_enabled=False)):
        ex = build_prospecting_export(result, account, lineage=lin)
    d = ex.to_dict()
    assert "lineage_export" not in d


def test_map_export_lineage_toggle() -> None:
    result = {
        "evidence_id": "E1",
        "confidence_tier": "HIGH",
        "confidence_score": 85,
        "risk_factors": [],
        "recommended_actions": [],
        "judge_pass": True,
        "judge_audit_score": 4.0,
    }
    lin = LineageExportBlock(map_run_id="m1", evidence_id="E1")
    with patch("src.integrations.export.load_config", return_value=_cfg(export_lineage_enabled=True)):
        ex_on = build_map_export(result, threshold_rationale="t", lineage=lin)
    assert ex_on.to_dict().get("lineage_export") is not None
    with patch("src.integrations.export.load_config", return_value=_cfg(export_lineage_enabled=False)):
        ex_off = build_map_export(result, threshold_rationale="t", lineage=lin)
    assert "lineage_export" not in ex_off.to_dict()
