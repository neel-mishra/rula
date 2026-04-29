"""
TelemetryAgent — emits metrics/events/traces and health anomalies.
Publishes stage completion/failure events with correlation IDs and timing.
"""

from __future__ import annotations

import structlog
from opentelemetry import metrics, trace

from core.schemas.contracts import TaskContext, TelemetryEvent
from subagents.base import BaseAgent

log = structlog.get_logger(__name__)

tracer = trace.get_tracer("inbox-chief-of-staff")
meter = metrics.get_meter("inbox-chief-of-staff")

# Metrics
_ingest_counter = meter.create_counter(
    "inbox.emails.ingested",
    description="Total emails ingested per mailbox",
)
_triage_counter = meter.create_counter(
    "inbox.triage.decisions",
    description="Triage decisions by outcome per mailbox",
)
_draft_counter = meter.create_counter(
    "inbox.drafts.generated",
    description="Drafts generated per mailbox",
)
_brief_counter = meter.create_counter(
    "inbox.briefs.delivered",
    description="Briefs delivered per mailbox",
)
_stage_latency = meter.create_histogram(
    "inbox.stage.duration_ms",
    description="Stage execution latency in ms",
    unit="ms",
)
_error_counter = meter.create_counter(
    "inbox.stage.errors",
    description="Stage errors by type and mailbox",
)


class TelemetryAgent(BaseAgent[TelemetryEvent, None]):
    name = "telemetry_agent"

    async def _execute(self, task: TelemetryEvent) -> None:
        attrs = {
            "mailbox_id": str(task.mailbox_id),
            "stage": task.stage,
            "event_type": task.event_type,
        }

        if task.duration_ms is not None:
            _stage_latency.record(task.duration_ms, attributes=attrs)

        if task.event_type == "stage.completed":
            self._emit_completion_metric(task, attrs)
        elif task.event_type == "stage.failed":
            _error_counter.add(1, attributes=attrs)
            log.error(
                "stage.failed",
                stage=task.stage,
                mailbox_id=str(task.mailbox_id),
                correlation_id=task.correlation_id,
                extra=task.extra,
            )
        elif task.event_type == "stage.started":
            log.debug(
                "stage.started",
                stage=task.stage,
                correlation_id=task.correlation_id,
            )

        return None

    def _emit_completion_metric(self, task: TelemetryEvent, attrs: dict) -> None:
        stage = task.stage
        if stage == "ingestion_agent":
            _ingest_counter.add(1, attributes=attrs)
        elif stage == "triage_agent":
            outcome = task.extra.get("outcome", "unknown")
            _triage_counter.add(1, attributes={**attrs, "outcome": outcome})
        elif stage == "draft_agent":
            _draft_counter.add(1, attributes=attrs)
        elif stage == "brief_agent":
            _brief_counter.add(1, attributes=attrs)


async def emit_telemetry(
    stage: str,
    event_type: str,
    task_context: TaskContext,
    duration_ms: float | None = None,
    extra: dict | None = None,
) -> None:
    """Convenience function for emitting telemetry from any agent or worker."""
    agent = TelemetryAgent()
    event = TelemetryEvent(
        user_id=task_context.user_id,
        mailbox_id=task_context.mailbox_id,
        correlation_id=task_context.correlation_id,
        policy_version=task_context.policy_version,
        stage=stage,
        event_type=event_type,
        duration_ms=duration_ms,
        extra=extra or {},
    )
    await agent.run(event)
