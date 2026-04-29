"""
LLM client — wraps Anthropic (primary) and OpenAI (fallback).
Enforces: kill switch, per-mailbox token budget, provider fallback.
"""

from __future__ import annotations

from typing import Any
from dataclasses import dataclass

import structlog

from core.config import settings
from core.observability.tracing import traced

log = structlog.get_logger(__name__)


@dataclass
class LLMResponse:
    content: str
    model_id: str
    input_tokens: int
    output_tokens: int
    provider: str


class ModelTier:
    """Task-based model selection: high-stakes vs low-stakes."""

    HIGH = "high"   # triage classification, draft generation, policy compilation
    LOW = "low"     # brief summaries, category tagging, simple extractions


class LLMClient:
    """Provider-agnostic LLM client with automatic fallback and tiered model routing."""

    def __init__(
        self,
        primary_provider: str | None = None,
        primary_model: str | None = None,
        fallback_provider: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self._primary_provider = primary_provider or settings.llm_primary_provider
        self._primary_model = primary_model or settings.llm_primary_model
        self._fallback_provider = fallback_provider or settings.llm_fallback_provider
        self._fallback_model = fallback_model or settings.llm_fallback_model
        self._cheap_provider = settings.llm_cheap_provider
        self._cheap_model = settings.llm_cheap_model

    @property
    def model_id(self) -> str:
        return self._primary_model

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        response_format: str = "text",  # "text" | "json"
        mailbox_id: str | None = None,
        tier: str = ModelTier.HIGH,
    ) -> LLMResponse:
        """
        Generate completion. Tries primary provider; falls back on error.
        Respects kill switch.
        """
        if settings.kill_switch_llm:
            raise RuntimeError("LLM kill switch is active — all LLM calls blocked")

        # Budget enforcement (skip if no mailbox context, e.g. global tasks)
        if mailbox_id:
            from core.llm.budget import check_budget, record_usage, BudgetExhaustedError

            await check_budget(mailbox_id)

        # Select model based on tier
        if tier == ModelTier.LOW:
            active_provider = self._cheap_provider
            active_model = self._cheap_model
        else:
            active_provider = self._primary_provider
            active_model = self._primary_model

        # Check cache first
        from core.llm.cache import get_cached_completion, set_cached_completion

        cached = await get_cached_completion(active_model, system, user)
        if cached:
            return LLMResponse(**cached)

        # Manual span for the full LLM call (provider attempts + fallback).
        # httpx auto-instrumentation will produce child spans for the actual
        # outbound HTTP requests. Span attributes follow the OTel semantic
        # convention prefix `llm.` (informational; no PII).
        llm_span_cm = traced(
            "llm.complete",
            **{
                "llm.provider": active_provider,
                "llm.model": active_model,
                "llm.tier": tier,
            },
        )
        llm_span_cm.__enter__()
        try:
            return await self._complete_inner(
                active_provider=active_provider,
                active_model=active_model,
                system=system,
                user=user,
                max_tokens=max_tokens,
                temperature=temperature,
                mailbox_id=mailbox_id,
            )
        finally:
            llm_span_cm.__exit__(None, None, None)

    async def _complete_inner(
        self,
        active_provider: str,
        active_model: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        mailbox_id: str | None,
    ) -> LLMResponse:
        from core.llm.budget import record_usage
        from core.llm.cache import set_cached_completion
        from core.llm.circuit_breaker import get_circuit_breaker

        cb = get_circuit_breaker()

        # Skip primary if circuit breaker tripped
        primary_exc = None
        if cb.is_available(active_provider):
            try:
                result = await self._call_provider(
                    provider=active_provider,
                    model=active_model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                cb.record_success(active_provider)
            except Exception as exc:
                cb.record_failure(active_provider)
                primary_exc = exc
                log.warning(
                    "llm.primary_failed_fallback",
                    provider=active_provider,
                    error=str(exc),
                )
                result = None
        else:
            log.warning("llm.circuit_breaker_open", provider=active_provider)
            primary_exc = RuntimeError(f"Circuit breaker open for {active_provider}")
            result = None

        if result is None:
            # Fallback
            if not self._fallback_provider:
                raise RuntimeError(
                    f"Primary LLM provider failed ({primary_exc}) and no fallback provider configured."
                )
            if cb.is_available(self._fallback_provider):
                try:
                    result = await self._call_provider(
                        provider=self._fallback_provider,
                        model=self._fallback_model,
                        system=system,
                        user=user,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    cb.record_success(self._fallback_provider)
                except Exception as fallback_exc:
                    cb.record_failure(self._fallback_provider)
                    log.error(
                        "llm.all_providers_failed",
                        primary_error=str(primary_exc),
                        fallback_error=str(fallback_exc),
                    )
                    raise RuntimeError(
                        f"All LLM providers failed. Primary: {primary_exc}. Fallback: {fallback_exc}"
                    ) from fallback_exc
            else:
                raise RuntimeError(
                    f"All LLM providers unavailable. Primary: {primary_exc}. "
                    f"Fallback circuit breaker open."
                )

        # Record usage after successful call
        if mailbox_id:
            await record_usage(mailbox_id, result.input_tokens, result.output_tokens)

        # Record USD cost against global + per-mailbox rollups (best-effort)
        from core.llm.budget import record_usage_usd
        await record_usage_usd(
            mailbox_id,
            result.model_id,
            result.input_tokens,
            result.output_tokens,
        )

        # Cache the response
        await set_cached_completion(
            result.model_id, system, user,
            {
                "content": result.content,
                "model_id": result.model_id,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "provider": result.provider,
            },
        )

        return result

    async def _call_provider(
        self,
        provider: str,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        if provider == "anthropic":
            return await self._call_anthropic(model, system, user, max_tokens, temperature)
        elif provider == "openai":
            return await self._call_openai(model, system, user, max_tokens, temperature)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    async def _call_anthropic(
        self, model: str, system: str, user: str, max_tokens: int, temperature: float
    ) -> LLMResponse:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        content = response.content[0].text if response.content else ""
        return LLMResponse(
            content=content,
            model_id=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            provider="anthropic",
        )

    async def _call_openai(
        self, model: str, system: str, user: str, max_tokens: int, temperature: float
    ) -> LLMResponse:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            content=content,
            model_id=model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            provider="openai",
        )


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
