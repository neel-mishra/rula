"""UX acceptance tests validating v1 plan criteria.

These tests validate the functional correctness of the pipeline outputs
and the structural properties of the UI render logic without requiring
a live Streamlit server.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.orchestrator.graph import run_map_verification, run_prospecting
from src.ui.components import audit_badge, confidence_pill, risk_chips
from src.ui.theme import AUDIT_COLORS, TIER_COLORS


# ---------------------------------------------------------------------------
# Acceptance Criterion: AE can complete prospecting and receive structured output
# ---------------------------------------------------------------------------

class TestProspectingAcceptance:
    def setup_method(self) -> None:
        accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
        self.account = accounts[0]
        self.result = run_prospecting(self.account, actor_role="user").model_dump()

    def test_has_email_with_subject_and_body(self) -> None:
        email = self.result.get("email", {})
        assert email.get("subject_line"), "Email must have a subject line"
        assert email.get("body"), "Email must have a body"
        assert len(email["body"]) > 20, "Body must be substantial"

    def test_has_matched_value_props(self) -> None:
        vps = self.result.get("matched_value_props", [])
        assert len(vps) >= 1, "Must have at least one matched value prop"
        for vp in vps:
            assert "value_prop" in vp
            assert "score" in vp
            assert "reasoning" in vp

    def test_has_quality_score(self) -> None:
        score = self.result.get("quality_score", 0)
        assert 0 <= score <= 5

    def test_has_discovery_questions(self) -> None:
        qs = self.result.get("discovery_questions", [])
        assert len(qs) >= 2, "Must have at least 2 discovery questions"

    def test_has_audit_fields(self) -> None:
        assert "judge_pass" in self.result
        assert "judge_audit_score" in self.result
        assert "judge_reasoning" in self.result

    def test_has_recommended_action_signal(self) -> None:
        assert "human_review_needed" in self.result

    def test_viewer_role_denied(self) -> None:
        with pytest.raises(PermissionError):
            run_prospecting(self.account, actor_role="viewer")


# ---------------------------------------------------------------------------
# Acceptance Criterion: MAP verification produces structured recommendation
# ---------------------------------------------------------------------------

class TestMapAcceptance:
    def setup_method(self) -> None:
        evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
        self.evidence_a = evidence[0]
        self.result = run_map_verification(
            self.evidence_a["evidence_id"],
            self.evidence_a["text"],
            actor_role="user",
        ).model_dump()

    def test_has_confidence_tier(self) -> None:
        tier = self.result.get("confidence_tier")
        assert tier in ("HIGH", "MEDIUM", "LOW")

    def test_has_confidence_score(self) -> None:
        score = self.result.get("confidence_score")
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_has_recommended_actions(self) -> None:
        actions = self.result.get("recommended_actions", [])
        assert len(actions) >= 1

    def test_has_audit_fields(self) -> None:
        assert "judge_pass" in self.result
        assert "judge_audit_score" in self.result

    def test_viewer_role_denied(self) -> None:
        with pytest.raises(PermissionError):
            run_map_verification(
                self.evidence_a["evidence_id"],
                self.evidence_a["text"],
                actor_role="viewer",
            )


# ---------------------------------------------------------------------------
# Acceptance Criterion: UI components render valid HTML without raw JSON
# ---------------------------------------------------------------------------

class TestComponentRendering:
    def test_confidence_pill_high(self) -> None:
        html = confidence_pill("HIGH", 85)
        assert "HIGH" in html
        assert "85" in html
        assert TIER_COLORS["HIGH"] in html

    def test_confidence_pill_medium(self) -> None:
        html = confidence_pill("MEDIUM", 55)
        assert "MEDIUM" in html
        assert TIER_COLORS["MEDIUM"] in html

    def test_confidence_pill_low(self) -> None:
        html = confidence_pill("LOW", 20)
        assert "LOW" in html
        assert TIER_COLORS["LOW"] in html

    def test_audit_badge_pass(self) -> None:
        html = audit_badge(True)
        assert "Ready to Send" in html
        assert AUDIT_COLORS["PASS"] in html

    def test_audit_badge_review(self) -> None:
        html = audit_badge(False)
        assert "Needs Review" in html
        assert AUDIT_COLORS["REVIEW"] in html

    def test_audit_badge_none(self) -> None:
        html = audit_badge(None)
        assert "Pending" in html

    def test_risk_chips_renders(self) -> None:
        html = risk_chips(["SECONDHAND_SOURCE", "BLOCKER_X"])
        assert "SECONDHAND_SOURCE" in html
        assert "BLOCKER_X" in html

    def test_risk_chips_empty(self) -> None:
        assert risk_chips([]) == ""


# ---------------------------------------------------------------------------
# Acceptance Criterion: All golden test cases still pass (no regression)
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_golden_map_tiers(self) -> None:
        evidence = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
        expected = {"A": "HIGH", "B": "LOW", "C": "MEDIUM"}
        for item in evidence:
            eid = item["evidence_id"]
            result = run_map_verification(eid, item["text"]).model_dump()
            assert result["confidence_tier"] == expected[eid], (
                f"Evidence {eid}: expected {expected[eid]}, got {result['confidence_tier']}"
            )

    def test_all_accounts_produce_output(self) -> None:
        accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
        for acct in accounts:
            result = run_prospecting(acct).model_dump()
            assert result.get("email"), f"Account {acct['account_id']} produced no email"
            assert result.get("matched_value_props"), f"Account {acct['account_id']} has no value props"


# ---------------------------------------------------------------------------
# Acceptance Criterion: Edge-case paths produce actionable UI states
# ---------------------------------------------------------------------------

class TestEdgeCasePaths:
    def test_kill_switch_produces_runtime_error(self) -> None:
        import os
        os.environ["RULA_DISABLE_PROSPECTING"] = "true"
        try:
            with pytest.raises(RuntimeError, match="disabled"):
                run_prospecting({"account_id": 1, "company": "X", "industry": "Y",
                                 "us_employees": 100, "contact": {"name": "A", "title": "B"},
                                 "health_plan": "C", "notes": "D"})
        finally:
            os.environ.pop("RULA_DISABLE_PROSPECTING", None)

    def test_permission_error_for_viewer(self) -> None:
        with pytest.raises(PermissionError):
            run_prospecting({"account_id": 1, "company": "X", "industry": "Y",
                             "us_employees": 100, "contact": {"name": "A", "title": "B"},
                             "health_plan": "C", "notes": "D"}, actor_role="viewer")
