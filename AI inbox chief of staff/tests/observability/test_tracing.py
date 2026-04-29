"""Tests for the OTel tracing bootstrap."""

from __future__ import annotations

import os

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from core.observability import tracing as tracing_module
from core.observability.tracing import init_tracing, traced


@pytest.fixture(autouse=True)
def _reset_tracing_state(monkeypatch):
    """Each test starts from a clean tracing state.

    The OTel API exposes the global tracer provider via a private
    ``_TRACER_PROVIDER`` slot; we reset our module-level guard and the API's
    once-set warning so successive tests can call ``init_tracing`` again.
    """
    tracing_module._reset_for_tests()

    # Snapshot original env so per-test monkeypatch.setenv/delenv applies cleanly.
    original = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    # Snapshot the API's private slot directly. Using get_tracer_provider() here
    # would resolve through the ProxyTracerProvider; restoring that proxy back
    # into _TRACER_PROVIDER causes proxy.get_tracer() to recurse on itself in
    # later tests. The slot's natural empty state is None.
    saved_slot = getattr(trace, "_TRACER_PROVIDER", None)
    # OTel's API logs a warning if set_tracer_provider is called twice in a
    # process; clear the once-flag so each test sees a fresh setup.
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]

    yield

    # Shut down any SDK provider the test installed so its BatchSpanProcessor
    # thread stops retrying exports to the (likely unreachable) endpoint.
    current_slot = getattr(trace, "_TRACER_PROVIDER", None)
    if isinstance(current_slot, TracerProvider) and current_slot is not saved_slot:
        current_slot.shutdown()

    # Restore env + slot state.
    tracing_module._reset_for_tests()
    if original is not None:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = original
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = saved_slot  # type: ignore[attr-defined]


def test_init_tracing_no_op_when_endpoint_unset(monkeypatch):
    """Without OTEL_EXPORTER_OTLP_ENDPOINT, init_tracing must do nothing.

    Specifically: it must not install a SDK TracerProvider (the API's default
    NoOp provider should still be in place).
    """
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    result = init_tracing("inbox-cos-test")

    assert result is False
    # The default API provider is a ProxyTracerProvider, not an SDK TracerProvider.
    provider = trace.get_tracer_provider()
    assert not isinstance(provider, TracerProvider), (
        "init_tracing should not install an SDK TracerProvider when endpoint is unset; "
        f"got {type(provider).__name__}"
    )


def test_init_tracing_configures_provider_when_endpoint_set(monkeypatch):
    """With the env var set, init_tracing must install an SDK TracerProvider."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    result = init_tracing("inbox-cos-test")

    assert result is True
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider), (
        f"expected SDK TracerProvider, got {type(provider).__name__}"
    )

    # service.name resource attr should be what we passed.
    resource_attrs = provider.resource.attributes
    assert resource_attrs.get("service.name") == "inbox-cos-test"
    assert "deployment.environment" in resource_attrs


def test_init_tracing_is_idempotent(monkeypatch):
    """Calling init_tracing twice must not replace the provider."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    assert init_tracing("inbox-cos-test") is True
    first_provider = trace.get_tracer_provider()

    # Second call returns True (already initialized) but doesn't swap providers.
    assert init_tracing("inbox-cos-test") is True
    assert trace.get_tracer_provider() is first_provider


def test_traced_context_manager_emits_named_span(monkeypatch):
    """`traced("name")` must produce a span with the given name and attributes."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    # Wire an in-memory exporter so we can assert on the emitted spans.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Mark our guard so init_tracing is treated as already-done by the helper —
    # we want to exercise `traced()` against this in-memory provider, not the
    # production OTLP exporter.
    tracing_module._INITIALIZED = True

    with traced("test.span", **{"llm.provider": "anthropic", "llm.tier": "high"}):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "test.span"
    assert span.attributes.get("llm.provider") == "anthropic"
    assert span.attributes.get("llm.tier") == "high"
