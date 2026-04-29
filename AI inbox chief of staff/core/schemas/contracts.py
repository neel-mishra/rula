"""
Typed stage contracts for the orchestrator/subagent pipeline.
Every task payload carries: user_id, mailbox_id, correlation_id, policy_version.
Every subagent response carries: ok, typed payload, warnings[], error envelope, meta.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# Base context — injected into every task/event
# ─────────────────────────────────────────────────────────────────────────────

class TaskContext(BaseModel):
    """Mandatory context carried by every task in the pipeline."""
    user_id: uuid.UUID
    mailbox_id: uuid.UUID
    correlation_id: str = Field(..., description="Trace ID linking all stages of one request")
    policy_version: str = Field(default="v1")
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


# ─────────────────────────────────────────────────────────────────────────────
# Error envelope
# ─────────────────────────────────────────────────────────────────────────────

class ErrorEnvelope(BaseModel):
    code: str
    message: str
    stage: str
    recoverable: bool = True
    detail: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Stage meta
# ─────────────────────────────────────────────────────────────────────────────

class StageMeta(BaseModel):
    run_id: str
    correlation_id: str
    stage: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Generic subagent response envelope
# ─────────────────────────────────────────────────────────────────────────────

class AgentResponse(BaseModel, Generic[T]):
    ok: bool
    payload: T | None = None
    warnings: list[str] = Field(default_factory=list)
    error: ErrorEnvelope | None = None
    meta: StageMeta


# ─────────────────────────────────────────────────────────────────────────────
# IngestionAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class IngestionTask(TaskContext):
    gmail_message_id: str
    gmail_history_id: str
    is_backfill: bool = False


class IngestionResult(BaseModel):
    email_id: uuid.UUID
    gmail_message_id: str
    is_duplicate: bool = False
    features_extracted: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# TriageAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class TriageTask(TaskContext):
    email_id: uuid.UUID
    gmail_message_id: str


class TriageResult(BaseModel):
    email_id: uuid.UUID
    outcome: str          # TriageOutcome value
    confidence: float
    method: str           # TriageMethod value
    rule_matched: str | None = None
    model_id: str | None = None
    reason_trace: str | None = None
    requires_mutation: bool = False
    mutation_type: str | None = None    # "archive" | "label_add" etc.
    label_id: str | None = None
    prompt_version: str | None = None   # variant pinned by A/B experiment


# ─────────────────────────────────────────────────────────────────────────────
# SafetyAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class SafetyCheckTask(TaskContext):
    email_id: uuid.UUID
    content: str
    check_type: str       # "prompt_injection" | "mutation_guard" | "policy_violation"


class SafetyCheckResult(BaseModel):
    passed: bool
    threats_detected: list[str] = Field(default_factory=list)
    sanitized_content: str | None = None
    blocked: bool = False
    block_reason: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# DraftAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class DraftTask(TaskContext):
    email_id: uuid.UUID
    gmail_thread_id: str
    style_profile_version: str | None = None


class DraftResult(BaseModel):
    draft_id: uuid.UUID
    gmail_draft_id: str | None = None
    draft_text: str
    subject_line: str | None = None
    grounding_score: float
    hallucination_flag: bool
    style_conformance_score: float


# ─────────────────────────────────────────────────────────────────────────────
# BriefAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class BriefTask(TaskContext):
    brief_id: uuid.UUID
    window: str           # "morning" | "afternoon"
    time_window_start: datetime
    time_window_end: datetime


class BriefResult(BaseModel):
    brief_id: uuid.UUID
    item_count: int
    delivery_email_id: str | None = None
    delivered_at: datetime | None = None


# ─────────────────────────────────────────────────────────────────────────────
# MemoryAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class MemoryWriteTask(TaskContext):
    feedback_event_id: uuid.UUID
    source: str


class MemoryWriteResult(BaseModel):
    memory_id: uuid.UUID
    memory_type: str
    scope: str
    confidence: float


class MemoryQueryTask(TaskContext):
    query: str
    memory_types: list[str] = Field(default_factory=list)
    top_k: int = 5


class MemoryQueryResult(BaseModel):
    memories: list[dict[str, Any]] = Field(default_factory=list)
    total_retrieved: int


# ─────────────────────────────────────────────────────────────────────────────
# PolicyAgent contracts
# ─────────────────────────────────────────────────────────────────────────────

class PolicyCompileTask(TaskContext):
    instruction_text: str
    source: str           # "assistant" | "feedback" | "onboarding"


class PolicyCompileResult(BaseModel):
    rules_created: int
    rules_updated: int
    policy_version: str
    needs_clarification: bool = False
    clarification_question: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# MutationGuardTask (SafetyAgent + MutationLedger integration)
# ─────────────────────────────────────────────────────────────────────────────

class MutationGuardTask(TaskContext):
    email_id: uuid.UUID
    mutation_type: str
    proposed_label_id: str | None = None
    confidence: float
    reason_trace: str
    triage_decision_id: uuid.UUID | None = None


class MutationGuardResult(BaseModel):
    allowed: bool
    ledger_id: uuid.UUID | None = None
    undo_token: str | None = None
    block_reason: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# TelemetryAgent — stage event emission
# ─────────────────────────────────────────────────────────────────────────────

class TelemetryEvent(TaskContext):
    stage: str
    event_type: str       # "stage.started" | "stage.completed" | "stage.failed"
    duration_ms: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
