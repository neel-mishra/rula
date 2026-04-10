"""Typed contracts for subagent boundaries (draft v0).

Every subagent result has strict Pydantic models with extra="forbid"
to catch field drift early. Shared primitives and error envelopes
enable consistent debuggability across stages.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "prospecting_contracts_v0.1"

STAGES = ("ingestion", "enrichment", "scoring", "explainability", "generation", "handoff")


class SubagentErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    stage: str
    recoverable: bool
    account_id: int | None = None
    retry_after_ms: int | None = None


class SignalAttributionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: str
    value_prop: str
    weight: int
    matched_text: str
    source_field: str


class StageMeta(BaseModel):
    """Shared timing/tracing fields embedded in every stage result."""
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_VERSION
    run_id: str = ""
    correlation_id: str = ""
    stage: str = ""
    started_at_ms: float = 0.0
    finished_at_ms: float = 0.0
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# IngestionAgent
# ---------------------------------------------------------------------------

class IngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="ingestion"))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    source: str = "test_data"
    accounts: list[dict] = Field(default_factory=list)
    account_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    dropped_count: int = 0
    ingestion_profile: str = "ingestion_v1"


# ---------------------------------------------------------------------------
# EnrichmentAgent
# ---------------------------------------------------------------------------

class EnrichmentRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int
    account_payload: dict
    enriched: dict
    row_error: SubagentErrorEnvelope | None = None


class EnrichmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="enrichment"))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    rows: list[EnrichmentRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ValuePropScoringAgent
# ---------------------------------------------------------------------------

class ScoringRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int
    matches: list[dict] = Field(default_factory=list)
    attributions: list[SignalAttributionRecord] = Field(default_factory=list)


class ValuePropScoringResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="scoring"))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    scoring_version: str = ""
    rows: list[ScoringRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ExplainabilityAgent
# ---------------------------------------------------------------------------

class ExplainabilityRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int
    value_prop: str
    explanation_text: str
    explanation_provider: str = "template"
    explanation_prompt_version: str = "v3"
    evidence_refs: list[str] = Field(default_factory=list)
    specificity_score: int = 0
    fallback_used: bool = False
    flags: list[str] = Field(default_factory=list)


class ExplainabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="explainability"))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    rows: list[ExplainabilityRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# GenerationAgent
# ---------------------------------------------------------------------------

class GenerationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int
    email: dict = Field(default_factory=dict)
    discovery_questions: list[str] = Field(default_factory=list)
    email_provider: str = ""
    questions_provider: str = ""
    email_prompt_version: str = "v3"
    questions_prompt_version: str = "v3"
    email_validation_passed: bool = True
    email_repair_attempted: bool = False
    email_fallback_used: bool = False
    questions_validation_passed: bool = True
    questions_repair_attempted: bool = False
    questions_fallback_used: bool = False
    context_source: str = "none"
    context_snippet: str = ""
    segment_label: str = ""
    emphasis_vp: str = ""
    competitor_token: str = ""
    wedge: str = ""
    policy_flags: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="generation"))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    rows: list[GenerationRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# HandoffAgent
# ---------------------------------------------------------------------------

class HandoffContractResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: StageMeta = Field(default_factory=lambda: StageMeta(stage="handoff"))
    ok: bool = True
    error: SubagentErrorEnvelope | None = None
    sequencer_payloads: list[dict] = Field(default_factory=list)
    crm_manifest: list[dict] = Field(default_factory=list)
    review_queue: list[dict] = Field(default_factory=list)
    archive_path: str | None = None
    telemetry_refs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ExecutionAgent aggregate
# ---------------------------------------------------------------------------

class ExecutionAgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    correlation_id: str = ""
    ok: bool = True
    milestones: dict[str, str] = Field(default_factory=dict)
    ingestion: IngestionResult | None = None
    enrichment: EnrichmentResult | None = None
    scoring: ValuePropScoringResult | None = None
    explainability: ExplainabilityResult | None = None
    generation: GenerationResult | None = None
    handoff: HandoffContractResult | None = None
    fatal_error: SubagentErrorEnvelope | None = None
    stage_errors: list[SubagentErrorEnvelope] = Field(default_factory=list)
