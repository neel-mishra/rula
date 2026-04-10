from __future__ import annotations

from src.telemetry.metrics import compute_connector_health_snapshot, compute_lifecycle_event_counts


def test_connector_health_snapshot_structure() -> None:
    snap = compute_connector_health_snapshot()
    assert "llm_by_provider" in snap
    assert "circuit_breakers" in snap
    assert "lifecycle" in snap
    assert isinstance(snap["lifecycle"], dict)


def test_lifecycle_counts_is_dict() -> None:
    assert isinstance(compute_lifecycle_event_counts(), dict)
