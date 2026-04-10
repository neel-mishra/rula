from __future__ import annotations

from pydantic import BaseModel, Field


class CampaignCommitment(BaseModel):
    campaign_type: str
    quarter: str
    year: int | None = None


class ParsedEvidence(BaseModel):
    evidence_id: str
    committer_name: str | None = None
    committer_title: str | None = None
    source_directness: str
    campaigns: list[CampaignCommitment] = Field(default_factory=list)
    total_quarters: int = 0
    commitment_year: int | None = None
    commitment_strategy: str | None = None
    commitment_ambiguities: list[str] = Field(default_factory=list)
    language_excerpt: str
    blockers: list[str] = Field(default_factory=list)


class VerificationOutput(BaseModel):
    evidence_id: str
    confidence_score: int = Field(ge=0, le=100)
    confidence_tier: str
    risk_factors: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    judge_pass: bool | None = None
    judge_audit_score: float | None = None
    correction_attempts_used: int = 0
    judge_reasoning: str | None = None
    scoring_version: str | None = None
    score_breakdown: dict | None = None
    parse_summary: dict | None = None
    # Lifecycle / correlation (MAP run and upstream prospecting linkage).
    map_run_id: str | None = None
    correlation_id: str | None = None
    prospecting_run_id: str | None = None
    account_id: int | None = None
    assignment_id: str | None = None
    opportunity_id: str | None = None
    outreach_message_id: str | None = None
    thread_id: str | None = None
