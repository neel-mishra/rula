from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _emit_circuit_transition(circuit_name: str, state: str, *, detail: str = "") -> None:
    """Emit a single telemetry row for breaker state changes (open/closed)."""
    try:
        from src.telemetry.events import TelemetryEvent, emit

        meta = {"circuit_name": circuit_name, "state": state, "connector_scope": circuit_name}
        if detail:
            meta["detail"] = detail
        emit(
            TelemetryEvent(
                event_type="circuit_state",
                pipeline=circuit_name,
                success=state == "closed",
                metadata=meta,
            )
        )
    except Exception as e:  # pragma: no cover - telemetry must not break callers
        logger.debug("circuit telemetry skipped: %s", e)


@dataclass
class CircuitBreaker:
    """In-process breaker for future LLM/provider calls (open after consecutive failures)."""

    name: str
    failure_threshold: int = 3
    recovery_seconds: float = 30.0
    _failures: int = 0
    _opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.recovery_seconds:
            self._opened_at = None
            self._failures = 0
            _emit_circuit_transition(self.name, "closed", detail="recovery_elapsed")
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            if self._opened_at is None:
                self._opened_at = time.monotonic()
                _emit_circuit_transition(self.name, "open", detail="threshold_reached")


# Shared breakers for demo wiring (deterministic agents do not trip these by default).
prospecting_breaker = CircuitBreaker("prospecting")
map_breaker = CircuitBreaker("map_verification")
