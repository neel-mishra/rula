"""SLO target definitions + status evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Operator(str, Enum):
    LE = "<="   # lower is better
    GE = ">="   # higher is better


class MetricStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"             # within 20% of target but not yet passing
    FAIL = "fail"
    NOT_MEASURED = "not_measured"   # too little data or no instrumentation


class MetricCategory(str, Enum):
    QUALITY = "quality"
    LATENCY = "latency"
    UNDO = "undo"
    RELIABILITY = "reliability"
    COST = "cost"


@dataclass(frozen=True)
class MetricTarget:
    id: str
    name: str
    category: MetricCategory
    target_value: float
    operator: Operator
    unit: str                 # "rate", "seconds", "usd_per_day", "dimensionless"
    description: str
    window_days: int = 7
    min_sample_size: int = 5


def _warn_band(target: MetricTarget) -> float:
    """Within 20% of target counts as WARN rather than FAIL."""
    return target.target_value * 0.2


def evaluate(value: float | None, target: MetricTarget) -> MetricStatus:
    """Given a current value and a target, return the status bucket."""
    if value is None:
        return MetricStatus.NOT_MEASURED
    band = _warn_band(target)
    if target.operator is Operator.LE:
        if value <= target.target_value:
            return MetricStatus.PASS
        if value <= target.target_value + band:
            return MetricStatus.WARN
        return MetricStatus.FAIL
    else:  # GE
        if value >= target.target_value:
            return MetricStatus.PASS
        if value >= target.target_value - band:
            return MetricStatus.WARN
        return MetricStatus.FAIL


@dataclass
class MetricReading:
    target: MetricTarget
    value: float | None
    sample_size: int
    status: MetricStatus
    note: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Target registry — one row per "Numeric Launch Targets" table entry
# ─────────────────────────────────────────────────────────────────────────────

TARGETS: dict[str, MetricTarget] = {
    # Quality & Safety
    "false_archive_rate": MetricTarget(
        id="false_archive_rate",
        name="False-archive rate (7d)",
        category=MetricCategory.QUALITY,
        target_value=0.005,   # 0.5%
        operator=Operator.LE,
        unit="rate",
        description=(
            "Share of archive mutations that were later undone by the user. "
            "Proxy for 'the system archived something it shouldn't have'."
        ),
    ),
    "false_brief_rate": MetricTarget(
        id="false_brief_rate",
        name="False-brief rate (7d)",
        category=MetricCategory.QUALITY,
        target_value=0.01,    # 1.0%
        operator=Operator.LE,
        unit="rate",
        description=(
            "Share of brief-only triage decisions later corrected by the user "
            "to inbox_keep or protected."
        ),
    ),
    "draft_grounding_failure_rate": MetricTarget(
        id="draft_grounding_failure_rate",
        name="Draft grounding-failure rate (7d)",
        category=MetricCategory.QUALITY,
        target_value=0.015,   # 1.5%
        operator=Operator.LE,
        unit="rate",
        description=(
            "Share of drafts that were rejected for grounding_score < 0.4 or "
            "flagged for hallucination."
        ),
    ),
    # Latency
    "ingest_to_triage_p95": MetricTarget(
        id="ingest_to_triage_p95",
        name="Ingest → triage latency p95",
        category=MetricCategory.LATENCY,
        target_value=60.0,
        operator=Operator.LE,
        unit="seconds",
        description="p95 time from email.received_at → triage_decision.created_at.",
    ),
    "ingest_to_triage_p99": MetricTarget(
        id="ingest_to_triage_p99",
        name="Ingest → triage latency p99",
        category=MetricCategory.LATENCY,
        target_value=180.0,
        operator=Operator.LE,
        unit="seconds",
        description="p99 time from email.received_at → triage_decision.created_at.",
    ),
    "draft_generation_p95": MetricTarget(
        id="draft_generation_p95",
        name="Draft generation latency p95",
        category=MetricCategory.LATENCY,
        target_value=45.0,
        operator=Operator.LE,
        unit="seconds",
        description=(
            "p95 time from email.received_at → draft.created_at for drafted "
            "emails."
        ),
    ),
    "brief_completion_rate": MetricTarget(
        id="brief_completion_rate",
        name="Brief generation completion rate",
        category=MetricCategory.RELIABILITY,
        target_value=0.995,
        operator=Operator.GE,
        unit="rate",
        description=(
            "Share of briefs that reached DELIVERED (or SKIPPED intentionally "
            "for empty windows)."
        ),
    ),
    "brief_timeliness_rate": MetricTarget(
        id="brief_timeliness_rate",
        name="Brief delivery timeliness (≤10 min of window)",
        category=MetricCategory.RELIABILITY,
        target_value=0.99,
        operator=Operator.GE,
        unit="rate",
        description=(
            "Share of delivered briefs that shipped within 10 min of "
            "scheduled_at."
        ),
    ),
    # Undo
    "undo_success_rate": MetricTarget(
        id="undo_success_rate",
        name="Undo success rate",
        category=MetricCategory.UNDO,
        target_value=0.999,
        operator=Operator.GE,
        unit="rate",
        description=(
            "Share of attempted undos with status=UNDONE (vs UNDO_FAILED)."
        ),
    ),
    "undo_execution_p95": MetricTarget(
        id="undo_execution_p95",
        name="Undo execution latency p95",
        category=MetricCategory.UNDO,
        target_value=30.0,
        operator=Operator.LE,
        unit="seconds",
        description=(
            "p95 time from mutation applied_at → undone_at for successful "
            "undos."
        ),
    ),
    # Safety
    "prompt_injection_pass_rate": MetricTarget(
        id="prompt_injection_pass_rate",
        name="Prompt-injection safety pass rate",
        category=MetricCategory.QUALITY,
        target_value=0.99,
        operator=Operator.GE,
        unit="rate",
        description=(
            "Computed at CI time over the adversarial suite; exposed here so "
            "the dashboard shows the last CI run."
        ),
    ),
    # Cost & efficiency
    "llm_cache_hit_rate": MetricTarget(
        id="llm_cache_hit_rate",
        name="LLM / embedding cache hit rate",
        category=MetricCategory.COST,
        target_value=0.4,
        operator=Operator.GE,
        unit="rate",
        description=(
            "End-of-month-1 target; requires cache-hit counters. Reports "
            "NOT_MEASURED until those counters exist in Redis."
        ),
    ),
    "cost_per_inbox_per_day": MetricTarget(
        id="cost_per_inbox_per_day",
        name="Average model cost per active inbox per day",
        category=MetricCategory.COST,
        target_value=0.75,
        operator=Operator.LE,
        unit="usd_per_day",
        description=(
            "Requires per-call cost accounting against the token-budget "
            "ledger; reports NOT_MEASURED until that pipeline is wired."
        ),
    ),
}
