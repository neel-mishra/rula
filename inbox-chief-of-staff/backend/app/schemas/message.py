"""Pydantic request/response schemas for messages and workflow state."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.message import IngestStatus, TriagePriority, WorkflowState


# ---------------------------------------------------------------------------
# TriageResult
# ---------------------------------------------------------------------------


class TriageResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    priority: TriagePriority
    confidence: float
    rationale: str
    labels: list[str]
    model_version: str
    created_at: datetime


# ---------------------------------------------------------------------------
# WorkflowRun
# ---------------------------------------------------------------------------


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    state: WorkflowState
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    triage_result: TriageResultResponse | None = None


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gmail_message_id: str
    gmail_thread_id: str
    subject: str
    sender_email: str
    sender_name: str
    received_at: datetime | None
    body_preview: str
    ingest_status: IngestStatus
    created_at: datetime
    workflow_runs: list[WorkflowRunResponse] = Field(default_factory=list)


class ListMessagesResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Triage override
# ---------------------------------------------------------------------------


class TriageOverrideRequest(BaseModel):
    priority: TriagePriority
    rationale: str | None = None
