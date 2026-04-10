from __future__ import annotations

import pytest

from src.config import AppConfig, validate_startup


def _cfg(**overrides: str) -> AppConfig:
    defaults = {
        "anthropic_api_key": "",
        "google_api_key": "",
        "model_primary": "claude",
        "model_fallback": "gemini",
        "generation_mode": "fast_mode",
        "environment": "local",
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_no_keys_warns_all() -> None:
    cfg = _cfg()
    warnings = validate_startup(cfg)
    assert any("No LLM provider" in w for w in warnings)


def test_claude_only() -> None:
    cfg = _cfg(anthropic_api_key="sk-real")
    assert cfg.has_claude
    assert not cfg.has_gemini
    assert cfg.resolve_provider() == "claude"
    assert cfg.resolve_fallback("claude") is None


def test_gemini_only() -> None:
    cfg = _cfg(google_api_key="AIza-real")
    assert cfg.has_gemini
    assert not cfg.has_claude
    assert cfg.resolve_provider("gemini") == "gemini"
    assert cfg.resolve_fallback("gemini") is None


def test_both_keys() -> None:
    cfg = _cfg(anthropic_api_key="sk-real", google_api_key="AIza-real")
    assert cfg.has_claude and cfg.has_gemini
    assert cfg.resolve_provider("claude") == "claude"
    assert cfg.resolve_provider("gemini") == "gemini"
    assert cfg.resolve_fallback("claude") == "gemini"
    assert cfg.resolve_fallback("gemini") == "claude"


def test_placeholder_not_real() -> None:
    cfg = _cfg(anthropic_api_key="your_anthropic_api_key_here")
    assert not cfg.has_claude


def test_production_no_keys_fails() -> None:
    cfg = _cfg(environment="production")
    with pytest.raises(RuntimeError, match="Production"):
        validate_startup(cfg)


def test_router_task_mapping() -> None:
    from src.providers.router import TASK_MODEL_MAP

    assert TASK_MODEL_MAP["email"] == "claude"
    assert TASK_MODEL_MAP["map_synthesis"] == "gemini"
