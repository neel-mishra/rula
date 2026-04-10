from __future__ import annotations

import json
from pathlib import Path

from src.agents.audit.correction import apply_map_correction
from src.agents.audit.judge import judge_map_verification, judge_prospecting
from src.orchestrator.graph import MAX_AUDIT_RETRIES, run_map_verification, run_prospecting
from src.schemas.account import Account, EnrichedAccount, Contact
from src.schemas.map_verification import ParsedEvidence, VerificationOutput
from src.schemas.prospecting import OutreachEmail, ProspectingOutput, ValuePropMatch


def test_map_golden_tiers_unchanged_with_audit() -> None:
    items = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    outputs = {i["evidence_id"]: run_map_verification(i["evidence_id"], i["text"]) for i in items}
    assert outputs["A"].confidence_tier == "HIGH"
    assert outputs["B"].confidence_tier == "LOW"
    assert outputs["C"].confidence_tier == "MEDIUM"


def test_audit_retries_bounded() -> None:
    assert MAX_AUDIT_RETRIES == 2


def test_apply_map_correction_caps_secondhand_high() -> None:
    parsed = ParsedEvidence(
        evidence_id="X",
        source_directness="ae_reported",
        campaigns=[],
        total_quarters=0,
        language_excerpt="",
        blockers=[],
    )
    prior = VerificationOutput(
        evidence_id="X",
        confidence_score=90,
        confidence_tier="HIGH",
        risk_factors=[],
        recommended_actions=[],
    )
    fixed = apply_map_correction(parsed, prior, "Slack from AE")
    assert fixed.confidence_tier == "MEDIUM"
    assert "AUDIT_TIER_CAP" in fixed.risk_factors


def test_judge_fails_synthetic_prospecting_without_company() -> None:
    account = Account(
        account_id=99,
        company="Acme Corp",
        industry="Retail",
        us_employees=100,
        contact=Contact(name="Jane", title="HR"),
        health_plan="Aetna",
        notes="",
    )
    enriched = EnrichedAccount(
        account=account,
        icp_fit_score=70,
        data_completeness_score=90,
        flags=[],
    )
    out = ProspectingOutput(
        account_id=99,
        matched_value_props=[
            ValuePropMatch(value_prop="employee_access", score=80, reasoning="test"),
        ],
        email=OutreachEmail(
            subject_line="Hello",
            body="Hi Jane,\n\nGeneric outreach with no company reference.\n\nWould you be open to a call?",
            cta="OK?",
        ),
        discovery_questions=["Q1?"],
        quality_score=4.0,
    )
    j = judge_prospecting(out, account, enriched)
    assert j.pass_audit is False
    assert j.correction_suggestions


def test_run_prospecting_sets_audit_fields() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    out = run_prospecting(accounts[0])
    assert out.judge_pass is not None
    assert out.judge_audit_score is not None
    assert out.correction_attempts_used <= MAX_AUDIT_RETRIES


def test_judge_map_blocks_secondhand_high() -> None:
    parsed = ParsedEvidence(
        evidence_id="Z",
        source_directness="ae_reported",
        campaigns=[],
        total_quarters=0,
        language_excerpt="",
        blockers=[],
    )
    bad = VerificationOutput(
        evidence_id="Z",
        confidence_score=90,
        confidence_tier="HIGH",
        risk_factors=[],
        recommended_actions=[],
    )
    j = judge_map_verification(bad, "Slack note from AE", parsed)
    assert j.pass_audit is False
