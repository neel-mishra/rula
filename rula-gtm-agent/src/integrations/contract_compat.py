"""Runtime contract / schema version checks for integration surfaces."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_LINEAGE_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})
SUPPORTED_INGEST_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0"})
SUPPORTED_EXPORT_CONTRACT_VERSIONS: frozenset[str] = frozenset({"1"})


class ContractVersionError(ValueError):
    """Raised when an inbound payload declares an unsupported schema/contract version."""


def _emit_contract_mismatch(component: str, declared: str, supported: str) -> None:
    try:
        from src.telemetry.events import TelemetryEvent, emit

        emit(
            TelemetryEvent(
                event_type="contract_version_mismatch",
                pipeline=component,
                success=False,
                error=f"unsupported_schema:{declared}",
                metadata={"declared": declared, "supported": supported, "component": component},
            )
        )
    except Exception as e:  # pragma: no cover
        logger.debug("contract telemetry skipped: %s", e)


def require_lineage_schema(version: str, *, component: str = "lineage_export") -> None:
    v = (version or "").strip()
    if v not in SUPPORTED_LINEAGE_SCHEMA_VERSIONS:
        supported = ",".join(sorted(SUPPORTED_LINEAGE_SCHEMA_VERSIONS))
        _emit_contract_mismatch(component, v, supported)
        raise ContractVersionError(
            f"{component}: unsupported lineage schema_version {v!r}; supported: {supported}"
        )


def require_ingest_schema(version: str, *, component: str = "ingest") -> None:
    v = (version or "").strip()
    if v not in SUPPORTED_INGEST_SCHEMA_VERSIONS:
        supported = ",".join(sorted(SUPPORTED_INGEST_SCHEMA_VERSIONS))
        _emit_contract_mismatch(component, v, supported)
        raise ContractVersionError(
            f"{component}: unsupported ingest schema_version {v!r}; supported: {supported}"
        )


def require_export_contract(version: str | None, *, component: str = "export") -> None:
    """Validate optional export bundle contract tag (``export_contract_version``)."""
    if version is None:
        return
    v = str(version).strip()
    if v not in SUPPORTED_EXPORT_CONTRACT_VERSIONS:
        supported = ",".join(sorted(SUPPORTED_EXPORT_CONTRACT_VERSIONS))
        _emit_contract_mismatch(component, v, supported)
        raise ContractVersionError(
            f"{component}: unsupported export_contract_version {v!r}; supported: {supported}"
        )


def validate_lineage_export_dict(data: dict[str, Any] | None) -> None:
    """Call before treating a lineage block as authoritative."""
    if not data:
        return
    require_lineage_schema(str(data.get("schema_version", "1.0")))
