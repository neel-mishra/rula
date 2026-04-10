from __future__ import annotations

from src.integrations.ingestion import (
    ClayWebhookConfig,
    build_clay_webhook_payload,
    load_clay_accounts_demo,
    load_test_accounts,
    load_test_accounts_raw,
)


def test_load_test_accounts_returns_all() -> None:
    accounts = load_test_accounts()
    assert len(accounts) == 8
    assert accounts[0].company == "Meridian Health Partners"


def test_load_test_accounts_raw_returns_dicts() -> None:
    raw = load_test_accounts_raw()
    assert isinstance(raw, list)
    assert isinstance(raw[0], dict)
    assert "account_id" in raw[0]


def test_clay_demo_returns_empty() -> None:
    accounts = load_clay_accounts_demo()
    assert accounts == []


def test_clay_webhook_config_from_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("CLAY_WEBHOOK_URL", raising=False)
    cfg = ClayWebhookConfig.from_env()
    assert cfg is None


def test_clay_webhook_config_from_env_present(monkeypatch) -> None:
    monkeypatch.setenv("CLAY_WEBHOOK_URL", "https://clay.test/hook")
    monkeypatch.setenv("CLAY_WORKSPACE_ID", "ws123")
    monkeypatch.setenv("CLAY_LIST_ID", "lst456")
    cfg = ClayWebhookConfig.from_env()
    assert cfg is not None
    assert cfg.webhook_url == "https://clay.test/hook"


def test_clay_webhook_payload_shape() -> None:
    cfg = ClayWebhookConfig(webhook_url="https://test", workspace_id="w1", list_id="l1")
    payload = build_clay_webhook_payload(cfg)
    assert payload["action"] == "import_account_list"
    assert payload["workspace_id"] == "w1"
    assert "fields_requested" in payload
    assert "company" in payload["fields_requested"]
