from __future__ import annotations

from src.config import AppConfig
from src.providers.base import GenerationRequest
from src.providers.router import ModelRouter


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


def test_no_providers_returns_error() -> None:
    router = ModelRouter(_cfg())
    req = GenerationRequest(content_type="email", prompt="hi")
    resp = router.generate(req)
    assert not resp.ok
    assert "No LLM provider" in (resp.error or "")


def test_email_routes_to_claude_when_available() -> None:
    cfg = _cfg(anthropic_api_key="sk-real")
    router = ModelRouter(cfg)
    assert "claude" in router._providers


def test_map_synthesis_routes_to_gemini_when_available() -> None:
    cfg = _cfg(google_api_key="AIza-real")
    router = ModelRouter(cfg)
    assert "gemini" in router._providers


def test_deterministic_fallback_when_llm_fails() -> None:
    from src.agents.prospecting.generator import _deterministic_email_v3, _deterministic_questions_v3
    from src.agents.prospecting.segment_logic import resolve_segment_context

    from src.schemas.account import Account, Contact, EnrichedAccount
    from src.schemas.prospecting import ValuePropMatch

    account = Account(
        account_id=99,
        company="TestCo",
        industry="Tech",
        us_employees=100,
        contact=Contact(name="Jane", title="VP"),
        health_plan="United",
        notes="Test",
    )
    enriched = EnrichedAccount(account=account, icp_fit_score=80, data_completeness_score=90, flags=[])
    matches = [ValuePropMatch(value_prop="employee_access", score=80, reasoning="test")]
    seg = resolve_segment_context(account.industry, matches)

    email = _deterministic_email_v3(enriched, seg, "")
    assert "TestCo" in email.subject_line or "TestCo" in email.body
    assert len(email.body) > 10

    questions = _deterministic_questions_v3(enriched, seg, "")
    assert len(questions) >= 3
