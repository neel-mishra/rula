"""Typed contracts for MAP subagent boundaries.

Reuses shared SubagentErrorEnvelope / StageMeta from contracts.py;
MAP-specific types model the parse → score → flag → audit pipeline.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.orchestrator.contracts import SubagentErrorEnvelope, StageMeta

MAP_CONTRACT_VERSION = "map_contracts_v0.1"

MAP_STAGES = ("parse", "score", "flag", "audit")


class MapParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="parse", contract_version=MAP_CONTRACT_VERSION))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    evidence_id: str = ""
    parsed: dict = Field(default_factory=dict)


class MapScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="score", contract_version=MAP_CONTRACT_VERSION))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    score: int = 0
    tier: str = ""
    risks: list[str] = Field(default_factory=list)
    breakdown: dict = Field(default_factory=dict)
    scoring_version: str = ""


class MapFlagResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="flag", contract_version=MAP_CONTRACT_VERSION))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    recommended_actions: list[str] = Field(default_factory=list)


class MapAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="audit", contract_version=MAP_CONTRACT_VERSION))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    judge_pass: bool | None = None
    judge_audit_score: float | None = None
    correction_attempts_used: int = 0
    judge_reasoning: str | None = None


class MapVerificationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = ""
    output: dict = Field(default_factory=dict)
    parsed_evidence: dict = Field(default_factory=dict)


class MapExecutionRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    correlation_id: str = ""
    ok: bool = True
    milestones: dict[str, str] = Field(default_factory=dict)
    parse: MapParseResult | None = None
    score: MapScoreResult | None = None
    flag: MapFlagResult | None = None
    audit: MapAuditResult | None = None
    fatal_error: SubagentErrorEnvelope | None = None
    stage_errors: list[SubagentErrorEnvelope] = Field(default_factory=list)
