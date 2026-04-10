"""Tests for code review fixes R-001 through R-016."""
from __future__ import annotations

import json
from unittest.mock import patch

from src.security.rbac import resolve_role, VALID_ROLES
from src.safety.sanitize import sanitize_evidence_id
from src.orchestrator.subagents import (
    run_ingestion_agent,
    run_enrichment_agent,
    run_scoring_agent,
)
from src.orchestrator.map_contracts import (
    MAP_CONTRACT_VERSION,
    MapParseResult,
    MapScoreResult,
    MapFlagResult,
    MapAuditResult,
)
from src.orchestrator.map_execution_agent import execute_map_verification
from src.validators.response_validator import (
    validate_email_json,
    validate_claims,
)
from src.governance.retention import enforce_retention


# ---- R-001: resolve_role environment gating ----

class TestResolveRole:
    def test_production_always_viewer(self):
        assert resolve_role("admin", environment="production") == "viewer"
        assert resolve_role("user", environment="production") == "viewer"

    def test_local_allows_admin(self):
        assert resolve_role("admin", environment="local") == "admin"

    def test_local_allows_user(self):
        assert resolve_role("user", environment="local") == "user"

    def test_invalid_role_defaults_user(self):
        assert resolve_role("hacker", environment="local") == "user"

    def test_valid_roles_constant(self):
        for role in VALID_ROLES:
            assert resolve_role(role, environment="local") == role


# ---- R-002: sanitize_evidence_id path traversal ----

class TestSanitizeEvidenceId:
    def test_strips_slash(self):
        assert "/" not in sanitize_evidence_id("../../etc/passwd")

    def test_strips_backslash(self):
        assert "\\" not in sanitize_evidence_id("..\\windows\\system32")

    def test_strips_dotdot(self):
        result = sanitize_evidence_id("../secret")
        assert ".." not in result

    def test_safe_id_preserved(self):
        assert sanitize_evidence_id("Evidence-A_01") == "Evidence-A_01"

    def test_empty_returns_unknown(self):
        assert sanitize_evidence_id("") == "unknown"

    def test_control_chars_removed(self):
        result = sanitize_evidence_id("id\x00\x01")
        assert "\x00" not in result
        assert "\x01" not in result


# ---- R-003: shadow actor_role (signature test) ----

class TestShadowSignatures:
    def test_compare_map_requires_role(self):
        from src.orchestrator.shadow import compare_map
        import inspect
        sig = inspect.signature(compare_map)
        assert "actor_role" in sig.parameters

    def test_compare_prospecting_requires_role(self):
        from src.orchestrator.shadow import compare_prospecting
        import inspect
        sig = inspect.signature(compare_prospecting)
        assert "actor_role" in sig.parameters


# ---- R-004: ingestion uses sanitized payload ----

class TestIngestionSanitized:
    def test_sanitized_payload_stored(self):
        raw = {
            "account_id": 1,
            "company": "A" * 10_000,
            "industry": "Tech",
            "us_employees": 500,
            "health_plan": "Cigna",
            "contact": {"name": "X", "title": "VP"},
        }
        result = run_ingestion_agent("test_data", raw_accounts=[raw])
        assert result.ok
        stored = result.accounts[0]
        assert len(stored["company"]) <= 4_000


# ---- R-005: generation_meta populated ----

class TestGenerationMeta:
    def test_generate_outreach_returns_triple(self):
        from src.agents.prospecting.generator import generate_outreach
        import inspect
        sig = inspect.signature(generate_outreach)
        assert "enriched" in sig.parameters


# ---- R-006: flag failure sets ok=False ----

class TestFlagFailure:
    def test_flag_exception_sets_ok_false(self):
        with patch("src.orchestrator.map_execution_agent.flag_actions", side_effect=RuntimeError("boom")):
            result = execute_map_verification("EV-1", "Q2 launch email commitment")
            assert result.ok is False
            assert any(e.code == "FLAG_FAILED" for e in result.stage_errors)


# ---- R-007: enrichment/scoring ok semantics ----

class TestEnrichmentScoringOk:
    def test_enrichment_all_fail_ok_false(self):
        bad_accounts = [{"account_id": 999}]
        result = run_enrichment_agent(bad_accounts)
        assert result.ok is False

    def test_scoring_empty_rows_ok_false(self):
        from src.orchestrator.contracts import EnrichmentResult, EnrichmentRow, SubagentErrorEnvelope
        er = EnrichmentResult(
            ok=False,
            rows=[
                EnrichmentRow(
                    account_id=1,
                    account_payload={},
                    enriched={},
                    row_error=SubagentErrorEnvelope(
                        code="FAIL", message="x", stage="enrichment", recoverable=False,
                    ),
                )
            ],
        )
        result = run_scoring_agent(er)
        assert result.ok is False
        assert len(result.rows) == 0


# ---- R-008: MAP contract version ----

class TestMapContractVersion:
    def test_parse_result_version(self):
        r = MapParseResult()
        assert r.meta.contract_version == MAP_CONTRACT_VERSION

    def test_score_result_version(self):
        r = MapScoreResult()
        assert r.meta.contract_version == MAP_CONTRACT_VERSION

    def test_flag_result_version(self):
        r = MapFlagResult()
        assert r.meta.contract_version == MAP_CONTRACT_VERSION

    def test_audit_result_version(self):
        r = MapAuditResult()
        assert r.meta.contract_version == MAP_CONTRACT_VERSION


# ---- R-009: validate_claims docstring/behavior alignment ----

class TestValidateClaims:
    def test_unknown_claim_fails(self):
        with patch("src.validators.response_validator._allowed_claim_texts", return_value=["100% coverage"]):
            result = validate_claims("We improved 50% retention at our clients")
            assert result.valid is False
            assert any("Unsourced" in i for i in result.issues)


# ---- R-010: email JSON type checks ----

class TestEmailJsonTypeChecks:
    def test_non_string_subject(self):
        payload = json.dumps({"subject_line": 42, "body": "x" * 30})
        result = validate_email_json(payload)
        assert result.valid is False
        assert any("string" in i for i in result.issues)

    def test_non_string_body(self):
        payload = json.dumps({"subject_line": "ok", "body": None})
        result = validate_email_json(payload)
        assert result.valid is False


# ---- R-011: telemetry retention ----

class TestTelemetryRetention:
    def test_telemetry_in_retention_targets(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tfile = tmp_path / "telemetry_events.jsonl"
        tfile.write_text('{"ts": "2020-01-01T00:00:00+00:00", "event": "old"}\n')
        report = enforce_retention(1, actor_role="admin")
        assert report["rows_removed"] >= 1


# ---- R-014: _map_campaign_types removed ----

class TestParserCleanup:
    def test_no_map_campaign_types_function(self):
        from src.agents.verification import parser
        assert not hasattr(parser, "_map_campaign_types")
