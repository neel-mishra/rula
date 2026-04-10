from __future__ import annotations

import logging
import time

from src.config import AppConfig
from src.integrations.connector_policy import LLM_PROVIDER, get_connector_policy
from src.providers.base import GenerationRequest, GenerationResponse, LLMProvider
from src.providers.claude_provider import ClaudeProvider
from src.providers.gemini_provider import GeminiProvider
from src.telemetry.ux_events import emit_generation

logger = logging.getLogger(__name__)

TASK_MODEL_MAP: dict[str, str] = {
    "email": "claude",
    "email_v3": "claude",
    "subject_line": "claude",
    "discovery_questions": "claude",
    "discovery_questions_v3": "claude",
    "rationale_summary": "claude",
    "value_prop_explanation": "gemini",
    "map_synthesis": "gemini",
    "threshold_justification": "gemini",
    "econ_scenario": "gemini",
}


class ModelRouter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._llm_policy = get_connector_policy(LLM_PROVIDER)
        self._providers: dict[str, LLMProvider] = {}
        if config.has_claude:
            self._providers["claude"] = ClaudeProvider()
        if config.has_gemini:
            self._providers["gemini"] = GeminiProvider()

    def generate(
        self,
        request: GenerationRequest,
        *,
        preferred_provider: str | None = None,
    ) -> GenerationResponse:
        preferred = preferred_provider or TASK_MODEL_MAP.get(
            request.content_type, self._config.model_primary
        )
        provider_name = self._config.resolve_provider(preferred)
        if provider_name is None:
            return GenerationResponse(
                text="",
                provider="none",
                model="none",
                prompt_version="v1",
                error="No LLM provider available; using deterministic fallback.",
            )
        provider = self._providers[provider_name]
        t0 = time.monotonic()
        resp = provider.generate(request)
        elapsed = (time.monotonic() - t0) * 1000
        emit_generation(
            pipeline=request.content_type,
            provider=resp.provider,
            content_type=request.content_type,
            success=resp.ok,
            duration_ms=elapsed,
            error=resp.error or "",
            policy_timeout_s=str(self._llm_policy.timeout_seconds),
            policy_max_retries=str(self._llm_policy.max_retries),
        )
        if resp.ok:
            return resp

        fallback_name = self._config.resolve_fallback(provider_name)
        if fallback_name and fallback_name in self._providers:
            logger.info("Falling back from %s to %s", provider_name, fallback_name)
            t1 = time.monotonic()
            resp2 = self._providers[fallback_name].generate(request)
            elapsed2 = (time.monotonic() - t1) * 1000
            resp2 = GenerationResponse(
                text=resp2.text,
                provider=resp2.provider,
                model=resp2.model,
                prompt_version=resp2.prompt_version,
                fallback_used=True,
                error=resp2.error,
            )
            emit_generation(
                pipeline=request.content_type,
                provider=resp2.provider,
                content_type=request.content_type,
                success=resp2.ok,
                fallback_used=True,
                duration_ms=elapsed2,
                error=resp2.error or "",
                policy_timeout_s=str(self._llm_policy.timeout_seconds),
                policy_max_retries=str(self._llm_policy.max_retries),
            )
            return resp2

        return resp
