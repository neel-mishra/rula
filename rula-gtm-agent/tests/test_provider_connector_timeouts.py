"""R-009: LLM clients receive timeout from connector policy."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.connector_policy import LLM_PROVIDER, get_connector_policy
from src.providers.base import GenerationRequest


@pytest.fixture
def gen_req() -> GenerationRequest:
    return GenerationRequest(
        prompt="hello",
        content_type="email",
        max_tokens=100,
        temperature=0.0,
        system="sys",
    )


def test_claude_provider_passes_anthropic_timeout(monkeypatch: pytest.MonkeyPatch, gen_req: GenerationRequest) -> None:
    mock_mod = MagicMock()
    inst = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text="ok")]
    inst.messages.create.return_value = msg
    mock_mod.Anthropic = MagicMock(return_value=inst)
    monkeypatch.setitem(sys.modules, "anthropic", mock_mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    from src.providers.claude_provider import ClaudeProvider

    ClaudeProvider().generate(gen_req)

    policy = get_connector_policy(LLM_PROVIDER)
    mock_mod.Anthropic.assert_called_once()
    kwargs = mock_mod.Anthropic.call_args.kwargs
    assert kwargs["timeout"] == policy.timeout_seconds


def test_gemini_provider_passes_http_options_timeout_ms(monkeypatch: pytest.MonkeyPatch, gen_req: GenerationRequest) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    policy = get_connector_policy(LLM_PROVIDER)
    expected_ms = max(1, int(policy.timeout_seconds * 1000))

    mock_client_ctor = MagicMock()
    fake = MagicMock()
    fake.models.generate_content.return_value = MagicMock(text="ok")
    mock_client_ctor.return_value = fake

    with patch("google.genai.Client", mock_client_ctor):
        from src.providers.gemini_provider import GeminiProvider

        GeminiProvider().generate(gen_req)

    mock_client_ctor.assert_called_once()
    kw = mock_client_ctor.call_args.kwargs
    assert kw["http_options"].timeout == expected_ms
