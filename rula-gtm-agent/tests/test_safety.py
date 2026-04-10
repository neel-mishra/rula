from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.orchestrator import graph as graph_mod
from src.safety.circuit import CircuitBreaker
from src.safety.dlq import log_failure
from src.safety.sanitize import redact_context_for_persistence, sanitize_account_payload, sanitize_evidence_text


@pytest.fixture(autouse=True)
def _reset_breakers() -> None:
    graph_mod.prospecting_breaker.record_success()
    graph_mod.map_breaker.record_success()
    yield
    graph_mod.prospecting_breaker.record_success()
    graph_mod.map_breaker.record_success()


def test_sanitize_strips_nul() -> None:
    t = sanitize_evidence_text("hello\x00world")
    assert "\x00" not in t
    assert "helloworld" in t or "hello" in t


def test_redact_context_strips_nested_secrets() -> None:
    raw = {"outer": {"api_key": "secret123", "safe": "x"}, "token": "t"}
    out = redact_context_for_persistence(raw)
    assert out["outer"]["api_key"] == "[REDACTED]"
    assert out["outer"]["safe"] == "x"
    assert out["token"] == "[REDACTED]"


def test_dlq_and_incidents_redact_before_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.safety import dlq as dlq_mod
    from src.safety import incidents as inc_mod

    monkeypatch.setattr(dlq_mod, "DLQ_PATH", tmp_path / "dlq.jsonl")
    monkeypatch.setattr(inc_mod, "INCIDENTS_PATH", tmp_path / "incidents.jsonl")
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        log_failure(
            pipeline="prospecting",
            error=e,
            context={"trace_id": "t1", "password": "nope", "nested": {"refresh_token": "rt"}},
        )
    dlq_line = (tmp_path / "dlq.jsonl").read_text(encoding="utf-8").strip()
    inc_line = (tmp_path / "incidents.jsonl").read_text(encoding="utf-8").strip()
    assert "nope" not in dlq_line
    assert "rt" not in dlq_line
    assert "[REDACTED]" in dlq_line
    assert "nope" not in inc_line
    assert '"trace_id": "t1"' in dlq_line


def test_sanitize_account_truncates_long_notes() -> None:
    long_notes = "x" * 5000
    out = sanitize_account_payload(
        {
            "account_id": 1,
            "company": "Co",
            "industry": "Retail",
            "us_employees": 10,
            "notes": long_notes,
        }
    )
    assert len(out["notes"]) <= 4000


def test_kill_switch_prospecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RULA_DISABLE_PROSPECTING", "1")
    with pytest.raises(RuntimeError, match="disabled"):
        graph_mod.run_prospecting(
            {
                "account_id": 1,
                "company": "Co",
                "industry": "Retail",
                "us_employees": 10,
            }
        )


def test_circuit_breaker_opens_after_failures() -> None:
    b = CircuitBreaker("test", failure_threshold=2, recovery_seconds=0.01)
    assert b.allow() is True
    b.record_failure()
    b.record_failure()
    assert b.allow() is False


def test_invalid_account_logs_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def capture(**kw: object) -> None:
        captured.append(kw)  # type: ignore[arg-type]

    monkeypatch.setattr(graph_mod, "log_failure", capture)
    with pytest.raises(Exception):
        graph_mod.run_prospecting({"account_id": "not-int"})
    assert captured
    assert captured[0]["pipeline"] == "prospecting"


def test_golden_map_still_passes_after_safety_layer() -> None:
    items = json.loads(Path("data/map_evidence.json").read_text(encoding="utf-8"))
    outs = {i["evidence_id"]: graph_mod.run_map_verification(i["evidence_id"], i["text"]) for i in items}
    assert outs["A"].confidence_tier == "HIGH"
    assert outs["B"].confidence_tier == "LOW"
    assert outs["C"].confidence_tier == "MEDIUM"
