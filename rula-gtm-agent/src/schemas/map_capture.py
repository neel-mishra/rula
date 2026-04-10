from __future__ import annotations

from pydantic import BaseModel, Field


class MapCampaignPlan(BaseModel):
    campaign_type: str
    quarter: str = Field(pattern=r"^Q[1-4]$")


class MapCaptureInput(BaseModel):
    evidence_id: str
    source_type: str
    committer_name: str | None = None
    committer_title: str | None = None
    commitment_language: str
    campaign_plan: list[MapCampaignPlan] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
