"""
BaseAgent — shared scaffolding for all vertical subagents.
Provides: telemetry emission, error envelope construction, kill-switch checks,
circuit-breaker hooks, and structured logging.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

import structlog

from core.config import settings
from core.schemas.contracts import AgentResponse, ErrorEnvelope, StageMeta, TaskContext

log = structlog.get_logger(__name__)

TTask = TypeVar("TTask", bound=TaskContext)
TResult = TypeVar("TResult")


class BaseAgent(ABC, Generic[TTask, TResult]):
    """
    Abstract base for all subagents.

    Subclasses implement `_execute(task) -> TResult`.
    The `run(task)` method wraps execution with:
      - kill-switch checks
      - structured error handling
      - telemetry timing
      - AgentResponse wrapping
    """

    name: str = "base_agent"

    def __init__(self) -> None:
        self._log = structlog.get_logger(self.__class__.__name__)

    async def run(self, task: TTask) -> AgentResponse[TResult]:
        """
        Public entry point. Enforces cross-cutting concerns around _execute().
        """
        started_at = datetime.now(tz=timezone.utc)
        t0 = time.perf_counter()
        correlation_id = task.correlation_id
        run_id = task.run_id

        bound_log = self._log.bind(
            agent=self.name,
            correlation_id=correlation_id,
            run_id=run_id,
            mailbox_id=str(task.mailbox_id),
        )

        # Kill-switch check
        kill_switch_triggered = self._check_kill_switches(task)
        if kill_switch_triggered:
            bound_log.warning("Kill switch active — skipping agent execution")
            return self._error_response(
                code="KILL_SWITCH_ACTIVE",
                message=f"Kill switch active for agent {self.name}",
                stage=self.name,
                recoverable=True,
                started_at=started_at,
                run_id=run_id,
                correlation_id=correlation_id,
            )

        bound_log.info("agent.started")

        try:
            result = await self._execute(task)
            duration_ms = (time.perf_counter() - t0) * 1000
            bound_log.info("agent.completed", duration_ms=round(duration_ms, 2))

            return AgentResponse(
                ok=True,
                payload=result,
                warnings=[],
                meta=StageMeta(
                    run_id=run_id,
                    correlation_id=correlation_id,
                    stage=self.name,
                    started_at=started_at,
                    completed_at=datetime.now(tz=timezone.utc),
                    duration_ms=round(duration_ms, 2),
                ),
            )

        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            bound_log.exception("agent.failed", duration_ms=round(duration_ms, 2), error=str(exc))
            return self._error_response(
                code=type(exc).__name__,
                message=str(exc),
                stage=self.name,
                recoverable=self._is_recoverable(exc),
                started_at=started_at,
                run_id=run_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
            )

    @abstractmethod
    async def _execute(self, task: TTask) -> TResult:
        """Implement agent logic here."""
        ...

    def _check_kill_switches(self, task: TTask) -> bool:  # noqa: ARG002
        """
        Override in subclasses to add agent-specific kill-switch logic.
        Return True if agent should be bypassed.
        """
        return False

    def _is_recoverable(self, exc: Exception) -> bool:  # noqa: ARG002
        """Determine if an exception should trigger retry vs DLQ routing."""
        # Default: all exceptions are potentially recoverable via retry
        return True

    def _error_response(
        self,
        code: str,
        message: str,
        stage: str,
        recoverable: bool,
        started_at: datetime,
        run_id: str,
        correlation_id: str,
        duration_ms: float = 0.0,
    ) -> AgentResponse[TResult]:
        return AgentResponse(
            ok=False,
            payload=None,
            warnings=[],
            error=ErrorEnvelope(
                code=code,
                message=message,
                stage=stage,
                recoverable=recoverable,
            ),
            meta=StageMeta(
                run_id=run_id,
                correlation_id=correlation_id,
                stage=stage,
                started_at=started_at,
                completed_at=datetime.now(tz=timezone.utc),
                duration_ms=round(duration_ms, 2),
            ),
        )
