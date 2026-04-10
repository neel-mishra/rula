from __future__ import annotations

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str | None = None
    title: str | None = None


class Account(BaseModel):
    account_id: int
    company: str
    industry: str
    us_employees: int = Field(ge=0)
    contact: Contact = Field(default_factory=Contact)
    health_plan: str | None = None
    notes: str = ""
    reachability_hint: int | None = Field(
        default=None,
        description="Optional 0–100 demo hint for queue ordering; not live CRM signal.",
        ge=0,
        le=100,
    )
    # Optional lifecycle IDs for cross-pipeline traceability (CRM / MAP handoff).
    assignment_id: str | None = None
    opportunity_id: str | None = None
    outreach_message_id: str | None = None
    thread_id: str | None = None


class EnrichedAccount(BaseModel):
    account: Account
    icp_fit_score: int = Field(ge=0, le=100)
    data_completeness_score: int = Field(ge=0, le=100)
    flags: list[str] = Field(default_factory=list)
