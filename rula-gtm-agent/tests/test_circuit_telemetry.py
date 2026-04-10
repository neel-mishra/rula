from __future__ import annotations

from src.safety.circuit import CircuitBreaker, _emit_circuit_transition
from src.telemetry.events import TelemetryEvent


def test_emit_circuit_transition_records_event(monkeypatch) -> None:
    captured: list[TelemetryEvent] = []

    def cap(ev: TelemetryEvent) -> None:
        captured.append(ev)

    monkeypatch.setattr("src.telemetry.events.emit", cap)
    _emit_circuit_transition("prospecting", "open", detail="unit")
    assert captured
    assert captured[0].event_type == "circuit_state"
    assert captured[0].metadata["state"] == "open"
    assert captured[0].metadata["connector_scope"] == "prospecting"


def test_breaker_emits_on_open_and_recovery(monkeypatch) -> None:
    captured: list[TelemetryEvent] = []

    def cap(ev: TelemetryEvent) -> None:
        captured.append(ev)

    monkeypatch.setattr("src.telemetry.events.emit", cap)
    b = CircuitBreaker("t_breaker", failure_threshold=2, recovery_seconds=0.01)
    b.record_failure()
    b.record_failure()
    assert any(e.metadata.get("state") == "open" for e in captured)
    assert not b.allow()
    import time

    time.sleep(0.02)
    assert b.allow()
    assert any(e.metadata.get("state") == "closed" for e in captured)
