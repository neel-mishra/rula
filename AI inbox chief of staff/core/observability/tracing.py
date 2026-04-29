"""
OpenTelemetry tracing bootstrap.

Wires the OTel SDK into the FastAPI app and worker entrypoints, with an OTLP
HTTP exporter pointed at the collector defined in `infra/otel-collector.yml`.

Design notes
------------
- ``init_tracing`` is a **no-op** when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset
  in the environment. This keeps unit tests, local CLIs, and dev runs that
  don't have a collector running unaffected — no spans are buffered, no
  background exporter thread is spawned.
- Auto-instrumentation is applied for FastAPI, SQLAlchemy, and httpx so the
  three big I/O sources (inbound HTTP, DB queries, outbound LLM/Gmail calls)
  produce spans without manual decoration on every call site.
- A small ``traced`` helper is exposed for cases where we want a manually
  named span (e.g. ``llm.complete``) with custom attributes.
- ``init_tracing`` is **idempotent** — calling it twice (e.g. once in the
  FastAPI lifespan and once when imported by a worker subprocess) won't
  re-install instrumentation or replace the global tracer provider.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import structlog

log = structlog.get_logger(__name__)


# Module-level guard so repeat calls don't double-install instrumentation.
_INITIALIZED: bool = False


def _is_enabled() -> bool:
    """Tracing is enabled iff the OTLP endpoint env var is set (non-empty)."""
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def init_tracing(service_name: str) -> bool:
    """
    Initialize OpenTelemetry tracing.

    No-op when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset. Otherwise:
      - Installs a ``TracerProvider`` with a ``BatchSpanProcessor`` writing to
        an OTLP/HTTP exporter pointing at the configured endpoint.
      - Attaches resource attributes (``service.name``,
        ``deployment.environment``).
      - Auto-instruments FastAPI, SQLAlchemy (sync + async), and httpx.

    Returns ``True`` if tracing was initialized, ``False`` if it was a no-op.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return True
    if not _is_enabled():
        log.debug("tracing.disabled", reason="OTEL_EXPORTER_OTLP_ENDPOINT unset")
        return False

    # Imports are local so the SDK is not loaded when tracing is disabled.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # Resolve environment from settings if available; fall back to env var.
    try:
        from core.config import settings
        environment = settings.otel_environment
    except Exception:
        environment = os.environ.get("OTEL_ENVIRONMENT", "dev")

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": environment,
        }
    )

    provider = TracerProvider(resource=resource)
    # OTLPSpanExporter picks up OTEL_EXPORTER_OTLP_ENDPOINT (and
    # OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS) from env.
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _install_auto_instrumentation()

    _INITIALIZED = True
    log.info(
        "tracing.initialized",
        service_name=service_name,
        environment=environment,
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )
    return True


def _install_auto_instrumentation() -> None:
    """Best-effort auto-instrumentation. Failures are logged, not raised."""
    # FastAPI: instrument the class so any later FastAPI() instantiation is
    # automatically traced. Workers don't import FastAPI, so this is a no-op
    # there even if the package is present.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("tracing.fastapi_instrument_failed", error=str(exc))

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("tracing.sqlalchemy_instrument_failed", error=str(exc))

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("tracing.httpx_instrument_failed", error=str(exc))


@contextmanager
def traced(span_name: str, **attributes) -> Iterator:
    """
    Context manager that opens a span ``span_name`` with the given attributes.

    Safe to use whether or not tracing is initialized — when no provider is
    configured this returns a no-op span from the OTel API's default tracer.

    Example::

        with traced("llm.complete", **{"llm.provider": "anthropic"}):
            ...
    """
    from opentelemetry import trace

    tracer = trace.get_tracer("inbox-cos")
    with tracer.start_as_current_span(span_name) as span:
        for k, v in attributes.items():
            if v is not None:
                try:
                    span.set_attribute(k, v)
                except Exception:
                    # Attribute values must be primitives; swallow oddballs.
                    span.set_attribute(k, str(v))
        yield span


def _reset_for_tests() -> None:
    """Test-only: clear the initialization guard.

    Production code should never call this. Tests use it to verify
    init_tracing's two branches (no-op vs configured) in isolation.
    """
    global _INITIALIZED
    _INITIALIZED = False
