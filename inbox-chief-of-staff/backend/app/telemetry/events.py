from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class TelemetryEvent:
    event_type: str
    agent_name: str
    workflow_run_id: str
    user_id: str
    input_hash: str
    output_hash: str
    confidence: float
    model_version: str
    duration_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _sha256(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()


class TelemetryEmitter:
    async def emit(self, event: TelemetryEvent, db=None) -> None:
        """Log event as structured JSON. Optionally persist to audit_events."""
        logger.info(
            "telemetry_event",
            event_type=event.event_type,
            agent_name=event.agent_name,
            workflow_run_id=event.workflow_run_id,
            user_id=event.user_id,
            confidence=event.confidence,
            model_version=event.model_version,
            duration_ms=event.duration_ms,
        )
        if db is not None:
            from app.repositories.audit_repo import AuditRepository
            audit_repo = AuditRepository(db)
            await audit_repo.create(
                user_id=event.user_id,
                event_type=event.event_type,
                action=f"{event.agent_name}:{event.event_type}",
                outcome="success",
                agent_name=event.agent_name,
                workflow_run_id=event.workflow_run_id,
                metadata={
                    "input_hash": event.input_hash,
                    "output_hash": event.output_hash,
                    "confidence": event.confidence,
                    "model_version": event.model_version,
                    "duration_ms": event.duration_ms,
                    **event.metadata,
                },
            )

    async def emit_agent_call(
        self,
        agent_name: str,
        workflow_run_id: str,
        user_id: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        confidence: float,
        model: str,
        duration_ms: int,
        db=None,
    ) -> None:
        event = TelemetryEvent(
            event_type="agent_call",
            agent_name=agent_name,
            workflow_run_id=workflow_run_id,
            user_id=user_id,
            input_hash=_sha256(input_data),
            output_hash=_sha256(output_data),
            confidence=confidence,
            model_version=model,
            duration_ms=duration_ms,
        )
        await self.emit(event, db=db)
