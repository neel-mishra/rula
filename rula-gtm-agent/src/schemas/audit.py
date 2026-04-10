from __future__ import annotations

from pydantic import BaseModel, Field


class JudgeResult(BaseModel):
    """Output of LLM-as-a-Judge (heuristic or API-backed)."""

    pass_audit: bool
    audit_score: float = Field(ge=0, le=5)
    reasoning: str
    correction_suggestions: list[str] = Field(default_factory=list)
    rubric_version: str = "v1-heuristic"
    judge_model: str = "heuristic-judge-v1"
