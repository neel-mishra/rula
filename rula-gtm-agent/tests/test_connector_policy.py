from __future__ import annotations

from src.integrations.connector_policy import (
    CONTEXT_COMPANY,
    HANDOFF_MAP,
    LLM_PROVIDER,
    get_connector_policy,
    policy_matrix,
)


def test_policy_matrix_contains_core_connectors() -> None:
    m = policy_matrix()
    assert LLM_PROVIDER in m
    assert m[LLM_PROVIDER].timeout_seconds > 0
    assert HANDOFF_MAP in m


def test_env_override_timeout(monkeypatch) -> None:
    monkeypatch.setenv("RULA_CONNECTOR_CONTEXT_COMPANY_TIMEOUT_S", "42")
    p = get_connector_policy(CONTEXT_COMPANY)
    assert p.timeout_seconds == 42.0


def test_unknown_connector_gets_defaults() -> None:
    p = get_connector_policy("custom_future_connector")
    assert p.timeout_seconds == 30.0
    assert p.max_retries == 1


