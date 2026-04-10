"""Tests for MAP contracts and execution agent."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.orchestrator.contracts import SubagentErrorEnvelope, StageMeta
from src.orchestrator.map_contracts import (
    MAP_STAGES,
    MapAuditResult,
    MapExecutionRunResult,
    MapFlagResult,
    MapParseResult,
    MapScoreResult,
)
from src.orchestrator.map_execution_agent import execute_map_verification


class TestMapContractSchemas:
    def test_map_parse_result_roundtrip(self):
        r = MapParseResult(evidence_id="A", parsed={"committer_name": "test"})
        d = r.model_dump()
        r2 = MapParseResult.model_validate(d)
        assert r2.evidence_id == "A"

    def test_map_score_result_roundtrip(self):
        r = MapScoreResult(score=75, tier="HIGH", risks=[], scoring_version="v1")
        d = r.model_dump()
        r2 = MapScoreResult.model_validate(d)
        assert r2.score == 75

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            MapParseResult(evidence_id="A", parsed={}, unexpected_field="bad")

    def test_shared_primitives_reused(self):
        err = SubagentErrorEnvelope(
            code="TEST", message="test", stage="parse", recoverable=True,
        )
        r = MapParseResult(ok=False, error=err)
        assert r.error.code == "TEST"

    def test_stage_meta_embedded(self):
        meta = StageMeta(stage="score", run_id="r1", correlation_id="c1")
        r = MapScoreResult(meta=meta, score=50, tier="MEDIUM")
        assert r.meta.stage == "score"
        assert r.meta.run_id == "r1"

    def test_execution_run_result_all_stages(self):
        r = MapExecutionRunResult(
            run_id="test",
            parse=MapParseResult(),
            score=MapScoreResult(),
            flag=MapFlagResult(),
            audit=MapAuditResult(),
        )
        assert r.ok is True
        assert r.parse is not None
        assert r.score is not None

    def test_map_stages_constant(self):
        assert MAP_STAGES == ("parse", "score", "flag", "audit")


class TestMapExecutionAgent:
    def test_execute_returns_complete_result(self):
        result = execute_map_verification("A", "Email from David Chen. Excited to move forward. Q2 launch email.")
        assert result.ok is True
        assert result.parse is not None
        assert result.parse.ok is True
        assert result.score is not None
        assert result.score.ok is True
        assert result.flag is not None
        assert result.flag.ok is True
        assert result.run_id
        assert result.correlation_id

    def test_execute_populates_milestones(self):
        result = execute_map_verification("B", "AE notes. Exploring options. Q3 at the earliest.")
        assert "parse" in result.milestones
        assert "score" in result.milestones
        assert "flag" in result.milestones

    def test_execute_scoring_breakdown(self):
        result = execute_map_verification("A", "Email from David Chen. Excited to move forward. Q2 launch email.")
        assert result.score is not None
        assert result.score.breakdown
        assert "base" in result.score.breakdown
