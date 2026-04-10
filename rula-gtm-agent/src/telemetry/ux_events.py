from __future__ import annotations

import logging

from src.telemetry.events import TelemetryEvent, emit

logger = logging.getLogger(__name__)


def emit_page_view(page: str, role: str) -> None:
    emit(TelemetryEvent(
        event_type="page_view",
        pipeline=page,
        metadata={"role": role},
    ))


def emit_action(action: str, pipeline: str, role: str, **extra: str) -> None:
    emit(TelemetryEvent(
        event_type="ux_action",
        pipeline=pipeline,
        metadata={"action": action, "role": role, **extra},
    ))


def emit_edge_case(category: str, pipeline: str, detail: str) -> None:
    emit(TelemetryEvent(
        event_type="edge_case",
        pipeline=pipeline,
        success=False,
        error=category,
        metadata={"detail": detail},
    ))


def emit_explainability_view(panel: str, pipeline: str) -> None:
    emit(TelemetryEvent(
        event_type="explainability_view",
        pipeline=pipeline,
        metadata={"panel": panel},
    ))


def emit_generation(
    pipeline: str,
    provider: str,
    content_type: str,
    success: bool,
    fallback_used: bool = False,
    duration_ms: float = 0.0,
    error: str = "",
    *,
    policy_timeout_s: str = "",
    policy_max_retries: str = "",
) -> None:
    meta: dict[str, str] = {"content_type": content_type}
    if policy_timeout_s:
        meta["policy_timeout_s"] = policy_timeout_s
    if policy_max_retries:
        meta["policy_max_retries"] = policy_max_retries
    emit(TelemetryEvent(
        event_type="generation_complete",
        pipeline=pipeline,
        provider=provider,
        fallback_used=fallback_used,
        success=success,
        duration_ms=duration_ms,
        error=error,
        metadata=meta,
    ))


def emit_adoption(action: str, pipeline: str, **extra: str) -> None:
    emit(TelemetryEvent(
        event_type="adoption",
        pipeline=pipeline,
        metadata={"action": action, **extra},
    ))


def emit_business_dna_usage(pipeline: str, slices_used: list[str]) -> None:
    """Emit telemetry for business DNA context consumption."""
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        meta = reg.telemetry_metadata()
        meta["slices_used"] = ",".join(slices_used)
        emit(TelemetryEvent(
            event_type="business_dna_usage",
            pipeline=pipeline,
            success=reg.bundle.loaded,
            metadata=meta,
        ))
    except Exception:
        emit(TelemetryEvent(
            event_type="business_dna_usage",
            pipeline=pipeline,
            success=False,
            metadata={"slices_used": ",".join(slices_used), "context_loaded": "False"},
        ))


def emit_context_fetch(
    pipeline: str,
    source_type: str,
    confidence: str,
    flags: list[str] | None = None,
    duration_ms: float = 0.0,
) -> None:
    emit(TelemetryEvent(
        event_type="context_fetch",
        pipeline=pipeline,
        duration_ms=duration_ms,
        success=source_type != "none",
        metadata={
            "source_type": source_type,
            "confidence": confidence,
            "flags": ",".join(flags or []),
        },
    ))


def emit_policy_validation(
    pipeline: str,
    content_type: str,
    passed: bool,
    repair_attempted: bool = False,
    fallback_used: bool = False,
    violations: list[str] | None = None,
) -> None:
    emit(TelemetryEvent(
        event_type="policy_validation",
        pipeline=pipeline,
        success=passed,
        metadata={
            "content_type": content_type,
            "repair_attempted": str(repair_attempted),
            "fallback_used": str(fallback_used),
            "violations": ",".join(violations or []),
        },
    ))
