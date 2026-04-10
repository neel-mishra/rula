"""Central registry for outbound connector reliability defaults (timeouts, retries, backoff).

Policies are **defaults** for production-style connectors; local stubs may ignore them.
Override per connector via env: ``RULA_CONNECTOR_<CONNECTOR_ID>_TIMEOUT_S``,
``RULA_CONNECTOR_<CONNECTOR_ID>_MAX_RETRIES``, ``RULA_CONNECTOR_<CONNECTOR_ID>_BACKOFF_S``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

# Stable connector identifiers (used in telemetry and docs).
LLM_PROVIDER: Final = "llm_provider"
CONTEXT_COMPANY: Final = "context_company"
HANDOFF_PROSPECTING: Final = "handoff_prospecting"
HANDOFF_MAP: Final = "handoff_map"
INGESTION: Final = "ingestion"


@dataclass(frozen=True)
class ConnectorPolicy:
    """Reliability parameters for a logical connector surface."""

    connector_id: str
    timeout_seconds: float
    max_retries: int
    backoff_base_seconds: float
    idempotency_scope: str  # "run_id" | "evidence_id" | "none"

    def with_env_overrides(self) -> "ConnectorPolicy":
        """Apply ``RULA_CONNECTOR_<ID>_*`` environment overrides."""
        cid = self.connector_id.upper()
        timeout = _env_float(f"RULA_CONNECTOR_{cid}_TIMEOUT_S", self.timeout_seconds)
        retries = _env_int(f"RULA_CONNECTOR_{cid}_MAX_RETRIES", self.max_retries)
        backoff = _env_float(f"RULA_CONNECTOR_{cid}_BACKOFF_S", self.backoff_base_seconds)
        return ConnectorPolicy(
            connector_id=self.connector_id,
            timeout_seconds=timeout,
            max_retries=retries,
            backoff_base_seconds=backoff,
            idempotency_scope=self.idempotency_scope,
        )


_DEFAULTS: dict[str, ConnectorPolicy] = {
    LLM_PROVIDER: ConnectorPolicy(
        connector_id=LLM_PROVIDER,
        timeout_seconds=120.0,
        max_retries=0,
        backoff_base_seconds=0.5,
        idempotency_scope="none",
    ),
    CONTEXT_COMPANY: ConnectorPolicy(
        connector_id=CONTEXT_COMPANY,
        timeout_seconds=10.0,
        max_retries=1,
        backoff_base_seconds=0.25,
        idempotency_scope="none",
    ),
    HANDOFF_PROSPECTING: ConnectorPolicy(
        connector_id=HANDOFF_PROSPECTING,
        timeout_seconds=60.0,
        max_retries=2,
        backoff_base_seconds=0.5,
        idempotency_scope="run_id",
    ),
    HANDOFF_MAP: ConnectorPolicy(
        connector_id=HANDOFF_MAP,
        timeout_seconds=60.0,
        max_retries=2,
        backoff_base_seconds=0.5,
        idempotency_scope="run_id",
    ),
    INGESTION: ConnectorPolicy(
        connector_id=INGESTION,
        timeout_seconds=30.0,
        max_retries=2,
        backoff_base_seconds=0.5,
        idempotency_scope="none",
    ),
}


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_connector_policy(connector_id: str) -> ConnectorPolicy:
    """Return the policy for *connector_id*, merged with optional env overrides."""
    base = _DEFAULTS.get(connector_id)
    if base is None:
        base = ConnectorPolicy(
            connector_id=connector_id,
            timeout_seconds=30.0,
            max_retries=1,
            backoff_base_seconds=0.5,
            idempotency_scope="none",
        )
    return base.with_env_overrides()


def policy_matrix() -> dict[str, ConnectorPolicy]:
    """All built-in connector IDs with env overrides applied (for docs/tests)."""
    return {k: get_connector_policy(k) for k in _DEFAULTS}
