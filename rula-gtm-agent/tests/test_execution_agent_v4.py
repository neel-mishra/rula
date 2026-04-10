"""Tests for v4 subagent contracts and execution agent."""
from __future__ import annotations


import pytest

from src.orchestrator.contracts import (
    CONTRACT_VERSION,
    EnrichmentResult,
    EnrichmentRow,
    ExecutionAgentRunResult,
    GenerationResult,
    GenerationRow,
    ExplainabilityResult,
    ExplainabilityRow,
    HandoffContractResult,
    IngestionResult,
    ScoringRow,
    SignalAttributionRecord,
    SubagentErrorEnvelope,
    ValuePropScoringResult,
)


class TestContractSchemas:
    """Verify that all contract models serialize/deserialize cleanly."""

    def test_error_envelope_fields(self):
        env = SubagentErrorEnvelope(
            code="TEST_ERROR", message="something broke",
            stage="ingestion", recoverable=True, account_id=42,
        )
        d = env.model_dump()
        assert d["code"] == "TEST_ERROR"
        assert d["recoverable"] is True
        assert d["account_id"] == 42

    def test_signal_attribution_record(self):
        rec = SignalAttributionRecord(
            signal="industry_health_system", value_prop="total_cost_of_care",
            weight=30, matched_text="Health System", source_field="industry",
        )
        d = rec.model_dump()
        assert d["weight"] == 30

    def test_ingestion_result_roundtrip(self):
        r = IngestionResult(
            ok=True, source="test_data",
            accounts=[{"account_id": 1, "company": "Acme"}],
            account_count=1, warnings=[], dropped_count=0,
        )
        raw = r.model_dump_json()
        r2 = IngestionResult.model_validate_json(raw)
        assert r2.account_count == 1
        assert r2.meta.contract_version == CONTRACT_VERSION

    def test_enrichment_result_roundtrip(self):
        row = EnrichmentRow(account_id=1, account_payload={"a": 1}, enriched={"b": 2})
        r = EnrichmentResult(rows=[row])
        raw = r.model_dump_json()
        r2 = EnrichmentResult.model_validate_json(raw)
        assert len(r2.rows) == 1

    def test_scoring_result_roundtrip(self):
        attr = SignalAttributionRecord(
            signal="s", value_prop="v", weight=5,
            matched_text="t", source_field="notes",
        )
        row = ScoringRow(account_id=1, matches=[{"value_prop": "x", "score": 50}],
                         attributions=[attr])
        r = ValuePropScoringResult(scoring_version="v3.0", rows=[row])
        raw = r.model_dump_json()
        r2 = ValuePropScoringResult.model_validate_json(raw)
        assert r2.scoring_version == "v3.0"
        assert len(r2.rows[0].attributions) == 1

    def test_explainability_result_roundtrip(self):
        row = ExplainabilityRow(
            account_id=1, value_prop="eap_upgrade",
            explanation_text="Because...", evidence_refs=["industry:University"],
            specificity_score=80,
        )
        r = ExplainabilityResult(rows=[row])
        raw = r.model_dump_json()
        r2 = ExplainabilityResult.model_validate_json(raw)
        assert r2.rows[0].specificity_score == 80

    def test_generation_result_roundtrip(self):
        row = GenerationRow(
            account_id=1, email={"subject_line": "Hi", "body": "...", "cta": "Reply"},
            discovery_questions=["Q1?", "Q2?", "Q3?"],
            email_provider="claude", questions_provider="gemini",
            context_source="linkedin", context_snippet="post",
            segment_label="health_system", emphasis_vp="total_cost_of_care",
            competitor_token="Lyra", wedge="EAP underperformance",
        )
        r = GenerationResult(rows=[row])
        raw = r.model_dump_json()
        r2 = GenerationResult.model_validate_json(raw)
        assert r2.rows[0].email_provider == "claude"

    def test_handoff_result_roundtrip(self):
        r = HandoffContractResult(
            sequencer_payloads=[{"id": 1}], crm_manifest=[{"id": 2}],
            review_queue=[], archive_path="/tmp/test",
        )
        raw = r.model_dump_json()
        r2 = HandoffContractResult.model_validate_json(raw)
        assert r2.archive_path == "/tmp/test"

    def test_execution_agent_run_result_roundtrip(self):
        r = ExecutionAgentRunResult(
            run_id="abc-123", correlation_id="xyz-456",
            ok=True, milestones={"ingestion": "complete"},
            stage_errors=[],
        )
        raw = r.model_dump_json()
        r2 = ExecutionAgentRunResult.model_validate_json(raw)
        assert r2.run_id == "abc-123"


class TestExtraForbid:
    """Contract models must reject unknown fields."""

    def test_ingestion_rejects_extra(self):
        with pytest.raises(Exception):
            IngestionResult(ok=True, source="x", extra_field="bad")

    def test_error_envelope_rejects_extra(self):
        with pytest.raises(Exception):
            SubagentErrorEnvelope(
                code="X", message="X", stage="X", recoverable=True, bonus="bad",
            )


class TestGoldenJsonSnapshots:
    """Verify stable field sets by checking serialized keys."""

    def test_ingestion_result_keys(self):
        r = IngestionResult()
        keys = set(r.model_dump().keys())
        expected = {"meta", "ok", "error", "source", "accounts",
                    "account_count", "warnings", "dropped_count", "ingestion_profile"}
        assert keys == expected

    def test_execution_agent_result_keys(self):
        r = ExecutionAgentRunResult()
        keys = set(r.model_dump().keys())
        expected = {"run_id", "correlation_id", "ok", "milestones",
                    "ingestion", "enrichment", "scoring", "explainability",
                    "generation", "handoff", "fatal_error", "stage_errors"}
        assert keys == expected


class TestSubagentIntegration:
    """Run the ingestion subagent against test data."""

    def test_ingestion_agent_with_test_data(self):
        from src.orchestrator.subagents import run_ingestion_agent
        result = run_ingestion_agent("test_data")
        assert result.ok
        assert result.account_count > 0
        assert result.meta.duration_ms > 0

    def test_enrichment_agent(self):
        from src.orchestrator.subagents import run_enrichment_agent, run_ingestion_agent
        ingestion = run_ingestion_agent("test_data")
        enrichment = run_enrichment_agent(ingestion.accounts)
        assert enrichment.ok
        assert len(enrichment.rows) == ingestion.account_count

    def test_scoring_agent(self):
        from src.orchestrator.subagents import (
            run_enrichment_agent,
            run_ingestion_agent,
            run_scoring_agent,
        )
        ingestion = run_ingestion_agent("test_data")
        enrichment = run_enrichment_agent(ingestion.accounts)
        scoring = run_scoring_agent(enrichment)
        assert scoring.ok
        assert len(scoring.rows) > 0
        for row in scoring.rows:
            assert len(row.matches) > 0

    def test_execution_agent_end_to_end(self):
        from src.orchestrator.execution_agent import execute_prospecting_run
        result = execute_prospecting_run("test_data")
        assert result.ok
        assert "ingestion" in result.milestones
        assert "enrichment" in result.milestones
        assert "scoring" in result.milestones
        assert result.ingestion is not None
        assert result.enrichment is not None
        assert result.scoring is not None
