"""
Circuit breaker for LLM providers — tracks failure rates and trips
after threshold. Auto-resets after cooldown period.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

import structlog

log = structlog.get_logger(__name__)

FAILURE_THRESHOLD = 5
WINDOW_SECONDS = 60
COOLDOWN_SECONDS = 120


@dataclass
class _ProviderState:
    failures: list[float] = field(default_factory=list)
    tripped_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self.tripped_at is None:
            return False
        elapsed = time.monotonic() - self.tripped_at
        if elapsed > COOLDOWN_SECONDS:
            self.tripped_at = None
            self.failures.clear()
            return False
        return True

    def record_failure(self, provider: str | None = None) -> None:
        now = time.monotonic()
        cutoff = now - WINDOW_SECONDS
        self.failures = [t for t in self.failures if t > cutoff]
        self.failures.append(now)
        if len(self.failures) >= FAILURE_THRESHOLD and self.tripped_at is None:
            self.tripped_at = now
            log.warning(
                "circuit_breaker.tripped",
                provider=provider,
                failures=len(self.failures),
                window=WINDOW_SECONDS,
            )
            try:
                from core.alerts import Severity, emit_alert
                emit_alert(
                    Severity.CRITICAL,
                    f"LLM circuit breaker tripped: {provider or 'unknown'}",
                    {
                        "provider": provider or "unknown",
                        "failures_in_window": len(self.failures),
                        "window_seconds": WINDOW_SECONDS,
                        "cooldown_seconds": COOLDOWN_SECONDS,
                    },
                )
            except Exception as exc:  # alerting must not re-raise
                log.warning("circuit_breaker.alert_failed", error=str(exc))

    def record_success(self) -> None:
        self.failures.clear()
        self.tripped_at = None


class CircuitBreaker:
    """Per-provider circuit breaker with sliding-window failure tracking."""

    def __init__(self) -> None:
        self._states: dict[str, _ProviderState] = defaultdict(_ProviderState)
        self._lock = Lock()

    def is_available(self, provider: str) -> bool:
        with self._lock:
            return not self._states[provider].is_open

    def record_failure(self, provider: str) -> None:
        with self._lock:
            self._states[provider].record_failure(provider=provider)

    def record_success(self, provider: str) -> None:
        with self._lock:
            self._states[provider].record_success()


_breaker = CircuitBreaker()


def get_circuit_breaker() -> CircuitBreaker:
    return _breaker
