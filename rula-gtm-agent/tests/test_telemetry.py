from __future__ import annotations

import json
from pathlib import Path

from src.telemetry.events import EVENTS_FILE, TelemetryEvent, emit, read_events
from src.telemetry.metrics import compute_metrics


def setup_function() -> None:
    if EVENTS_FILE.exists():
        EVENTS_FILE.unlink()


def test_emit_and_read() -> None:
    emit(TelemetryEvent(
        event_type="pipeline_complete",
        pipeline="prospecting",
        duration_ms=42.0,
        success=True,
    ))
    events = read_events()
    assert len(events) == 1
    assert events[0]["pipeline"] == "prospecting"
    assert events[0]["duration_ms"] == 42.0


def test_emit_strips_forbidden_metadata_keys() -> None:
    emit(TelemetryEvent(
        event_type="test",
        pipeline="prospecting",
        metadata={
            "run_id": "ok",
            "api_key": "SHOULD_NOT_PERSIST",
            "nested": {"x": 1},
        },
    ))
    events = read_events()
    assert len(events) == 1
    meta = events[0].get("metadata", {})
    assert meta.get("run_id") == "ok"
    assert "api_key" not in meta


def test_emit_strips_nested_forbidden_metadata_keys() -> None:
    """R-008: nested dict values cannot smuggle secrets under benign parent keys."""
    emit(TelemetryEvent(
        event_type="test",
        pipeline="prospecting",
        metadata={
            "run_id": "ok",
            "details": {"api_key": "NESTED_SECRET", "safe": "yes"},
            "extra": [{"password": "no"}, {"keep": 1}],
        },
    ))
    events = read_events()
    assert len(events) == 1
    meta = events[0].get("metadata", {})
    assert meta.get("run_id") == "ok"
    details = meta.get("details", {})
    assert "api_key" not in details
    assert details.get("safe") == "yes"
    extra = meta.get("extra", [])
    assert len(extra) == 2
    assert "password" not in extra[0]
    assert extra[1].get("keep") == 1


def test_compute_metrics_empty() -> None:
    m = compute_metrics("prospecting")
    assert m.total_runs == 0


def test_compute_metrics_with_events() -> None:
    emit(TelemetryEvent(event_type="pipeline_complete", pipeline="prospecting", duration_ms=100, success=True))
    emit(TelemetryEvent(event_type="pipeline_complete", pipeline="prospecting", duration_ms=200, success=True))
    emit(TelemetryEvent(event_type="pipeline_complete", pipeline="prospecting", duration_ms=50, success=False, error="boom"))
    m = compute_metrics("prospecting")
    assert m.total_runs == 3
    assert m.success_count == 2
    assert m.failure_count == 1
    assert m.avg_duration_ms > 0


def test_prospecting_emits_telemetry() -> None:
    accounts = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    from src.orchestrator.graph import run_prospecting
    run_prospecting(accounts[0])
    events = read_events()
    pipeline_events = [e for e in events if e["event_type"] == "pipeline_complete" and e["pipeline"] == "prospecting"]
    assert len(pipeline_events) >= 1
    assert pipeline_events[-1]["success"] is True


def teardown_function() -> None:
    if EVENTS_FILE.exists():
        EVENTS_FILE.unlink()
