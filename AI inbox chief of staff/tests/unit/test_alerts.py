"""Unit tests for incident alert routing."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core.alerts import Severity
from core.alerts.router import AlertRouter
from core.alerts.sinks import PagerDutySink, SlackSink


@dataclass
class _RecordingSink:
    name: str = "recording"
    calls: list[tuple[Severity, str, dict | None]] = field(default_factory=list)
    succeed: bool = True

    def send(self, severity, title, details=None):
        self.calls.append((severity, title, details))
        return self.succeed


class TestAlertRouter:
    def test_emit_with_no_sinks_is_noop(self):
        router = AlertRouter()
        result = router.emit(Severity.WARNING, "hello")
        assert result == {}

    def test_emit_fans_out_to_all_sinks(self):
        s1 = _RecordingSink(name="a")
        s2 = _RecordingSink(name="b")
        router = AlertRouter([s1, s2])
        result = router.emit(Severity.CRITICAL, "boom", {"k": "v"})
        assert result == {"a": True, "b": True}
        assert s1.calls == [(Severity.CRITICAL, "boom", {"k": "v"})]
        assert s2.calls == [(Severity.CRITICAL, "boom", {"k": "v"})]

    def test_sink_that_raises_does_not_break_others(self):
        @dataclass
        class _ExplodingSink:
            name: str = "bomb"
            def send(self, *a, **kw):
                raise RuntimeError("boom")

        ok = _RecordingSink(name="ok")
        router = AlertRouter([_ExplodingSink(), ok])
        result = router.emit(Severity.INFO, "t")
        assert result == {"bomb": False, "ok": True}
        assert len(ok.calls) == 1

    def test_sink_returning_false_captured(self):
        failing = _RecordingSink(name="fail", succeed=False)
        router = AlertRouter([failing])
        result = router.emit(Severity.WARNING, "t")
        assert result == {"fail": False}


class TestSlackSink:
    def test_success_returns_true(self, monkeypatch):
        sent: list[tuple[str, dict]] = []

        def fake_post(url, payload):
            sent.append((url, payload))
            return 200

        monkeypatch.setattr("core.alerts.sinks._post_json", fake_post)

        sink = SlackSink("https://hooks.slack.test/webhook")
        ok = sink.send(Severity.CRITICAL, "trouble", {"thing": "broke"})
        assert ok is True
        assert len(sent) == 1
        assert sent[0][0] == "https://hooks.slack.test/webhook"
        assert "CRITICAL" in sent[0][1]["text"]
        assert "trouble" in sent[0][1]["text"]

    def test_http_error_returns_false(self, monkeypatch):
        monkeypatch.setattr("core.alerts.sinks._post_json", lambda u, p: 500)
        sink = SlackSink("https://x")
        assert sink.send(Severity.WARNING, "t") is False

    def test_transport_error_returns_false(self, monkeypatch):
        def raise_err(*a, **kw):
            raise OSError("network down")

        monkeypatch.setattr("core.alerts.sinks._post_json", raise_err)
        sink = SlackSink("https://x")
        assert sink.send(Severity.WARNING, "t") is False


class TestPagerDutySink:
    def test_only_pages_on_critical(self, monkeypatch):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "core.alerts.sinks._post_json",
            lambda u, p: calls.append((u, p)) or 202,
        )
        sink = PagerDutySink(routing_key="rk")
        # INFO / WARNING are dropped silently (returned True, no POST)
        assert sink.send(Severity.INFO, "x") is True
        assert sink.send(Severity.WARNING, "x") is True
        assert calls == []
        # CRITICAL triggers a POST
        assert sink.send(Severity.CRITICAL, "page me", {"k": 1}) is True
        assert len(calls) == 1
        assert calls[0][1]["routing_key"] == "rk"
        assert calls[0][1]["event_action"] == "trigger"
        assert calls[0][1]["payload"]["summary"] == "page me"

    def test_transport_error_returns_false(self, monkeypatch):
        def raise_err(*a, **kw):
            raise OSError("timeout")
        monkeypatch.setattr("core.alerts.sinks._post_json", raise_err)
        sink = PagerDutySink(routing_key="rk")
        assert sink.send(Severity.CRITICAL, "t") is False


class TestCircuitBreakerAlert:
    def test_trip_emits_critical_alert(self, monkeypatch):
        from core.llm.circuit_breaker import CircuitBreaker, FAILURE_THRESHOLD
        from core.alerts import Severity

        captured: list[tuple[Severity, str, dict]] = []

        def fake_emit(severity, title, details=None):
            captured.append((severity, title, details))
            return {}

        # Patch the module where it's imported (core.alerts namespace)
        import core.alerts as alerts_mod
        monkeypatch.setattr(alerts_mod, "emit_alert", fake_emit)

        breaker = CircuitBreaker()
        for _ in range(FAILURE_THRESHOLD):
            breaker.record_failure("anthropic")

        assert not breaker.is_available("anthropic")
        assert len(captured) == 1
        severity, title, details = captured[0]
        assert severity == Severity.CRITICAL
        assert "anthropic" in title
        assert details["provider"] == "anthropic"
