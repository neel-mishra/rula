from __future__ import annotations

from pydantic import BaseModel, Field


class ValuePropMatch(BaseModel):
    value_prop: str
    score: int = Field(ge=0, le=100)
    reasoning: str


class OutreachEmail(BaseModel):
    subject_line: str
    body: str
    cta: str


class GenerationMeta(BaseModel):
    """Stage 4 provenance fields for explainability / audit."""
    context_source: str = "none"
    context_snippet: str = ""
    context_url: str = ""
    segment_label: str = ""
    emphasis_vp: str = ""
    competitor_token: str = ""
    wedge: str = ""
    email_provider: str = ""
    email_prompt_version: str = "v3"
    email_validation_passed: bool = True
    email_repair_attempted: bool = False
    email_fallback_used: bool = False
    questions_provider: str = ""
    questions_prompt_version: str = "v3"
    questions_validation_passed: bool = True
    questions_repair_attempted: bool = False
    questions_fallback_used: bool = False
    scoring_version: str = ""
    policy_flags: list[str] = Field(default_factory=list)


class ProspectingOutput(BaseModel):
    account_id: int
    matched_value_props: list[ValuePropMatch]
    email: OutreachEmail
    discovery_questions: list[str]
    quality_score: float = Field(ge=0, le=5)
    human_review_needed: bool = False
    skipped: bool = False
    skip_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    judge_pass: bool | None = None
    judge_audit_score: float | None = None
    correction_attempts_used: int = 0
    judge_reasoning: str | None = None
    generation_meta: GenerationMeta = Field(default_factory=GenerationMeta)
    # Lifecycle / correlation (prospecting run and CRM thread linkage).
    correlation_id: str | None = None
    prospecting_run_id: str | None = None
    assignment_id: str | None = None
    opportunity_id: str | None = None
    outreach_message_id: str | None = None
    thread_id: str | None = None
