"""Gate 6 resilience — retry, fallback, and circuit-breaker behavior.

Covers:
  - LLM primary failure → fallback provider used (Anthropic → OpenAI per the
    actual code wiring in core/llm/client.py).
  - 5 consecutive failures within the sliding window trip the breaker.
  - After the cooldown elapses (we patch `time.monotonic` rather than wall-
    sleeping for 120s), the breaker auto-resets on the next is_open check;
    a successful call closes it; a subsequent failure re-trips it.
  - Gmail rate limiter: per-mailbox token bucket exhaustion raises
    GmailRateLimitError; isolation between mailboxes is preserved (one hot
    mailbox does not starve another).

Mocks:
  - core.llm.client._call_provider patched at the method level so we never
    hit Anthropic/OpenAI HTTP.
  - core.llm.budget / cache helpers neutralized for the fallback test.
  - core.llm.circuit_breaker.time.monotonic patched for cooldown tests.
  - core.gmail.rate_limiter._get_redis returns a fake async client per test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm.circuit_breaker import (
    COOLDOWN_SECONDS,
    FAILURE_THRESHOLD,
    CircuitBreaker,
)


# ──────────────────────── circuit breaker — direct ───────────────────────


class TestCircuitBreakerStateTransitions:
    def test_under_threshold_does_not_trip(self):
        cb = CircuitBreaker()
        for _ in range(FAILURE_THRESHOLD - 1):
            cb.record_failure("anthropic")
        assert cb.is_available("anthropic") is True

    def test_n_consecutive_failures_trips(self):
        cb = CircuitBreaker()
        for _ in range(FAILURE_THRESHOLD):
            cb.record_failure("anthropic")
        assert cb.is_available("anthropic") is False

    def test_cooldown_then_half_open_success_closes_circuit(self):
        """Patch the breaker's clock so we don't wall-sleep COOLDOWN_SECONDS."""
        cb = CircuitBreaker()

        # Trip the breaker at simulated t=0.
        with patch("core.llm.circuit_breaker.time.monotonic", return_value=0.0):
            for _ in range(FAILURE_THRESHOLD):
                cb.record_failure("anthropic")
            assert cb.is_available("anthropic") is False

        # Just inside cooldown: still open.
        with patch(
            "core.llm.circuit_breaker.time.monotonic",
            return_value=COOLDOWN_SECONDS - 1.0,
        ):
            assert cb.is_available("anthropic") is False

        # Past cooldown: is_open returns False (auto-reset). This is the
        # implicit "half-open probe" — the next call is allowed through.
        with patch(
            "core.llm.circuit_breaker.time.monotonic",
            return_value=COOLDOWN_SECONDS + 1.0,
        ):
            assert cb.is_available("anthropic") is True

        # Probe succeeds → record_success keeps state closed.
        cb.record_success("anthropic")
        assert cb.is_available("anthropic") is True

    def test_cooldown_then_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker()

        # Trip at t=0.
        with patch("core.llm.circuit_breaker.time.monotonic", return_value=0.0):
            for _ in range(FAILURE_THRESHOLD):
                cb.record_failure("openai")
            assert cb.is_available("openai") is False

        # Past cooldown → breaker auto-resets on next probe.
        with patch(
            "core.llm.circuit_breaker.time.monotonic",
            return_value=COOLDOWN_SECONDS + 5.0,
        ):
            assert cb.is_available("openai") is True

            # Half-open probe fails → record THRESHOLD failures again to re-trip.
            for _ in range(FAILURE_THRESHOLD):
                cb.record_failure("openai")
            assert cb.is_available("openai") is False

    def test_per_provider_isolation(self):
        """Tripping anthropic must not affect openai."""
        cb = CircuitBreaker()
        for _ in range(FAILURE_THRESHOLD):
            cb.record_failure("anthropic")
        assert cb.is_available("anthropic") is False
        assert cb.is_available("openai") is True


# ─────────────────────── LLM client primary→fallback ─────────────────────


class TestLLMPrimaryFallback:
    """Verify the primary→fallback wiring in core/llm/client.py.

    We patch `_call_provider` (the lowest-level hook before the real
    Anthropic/OpenAI SDK call) so the test exercises the real fallback
    decision logic without hitting the network.
    """

    @pytest.mark.asyncio
    async def test_anthropic_failure_falls_back_to_openai(self):
        from core.llm.client import LLMClient, LLMResponse

        provider_calls: list[str] = []

        async def fake_call_provider(
            self, *, provider, model, system, user, max_tokens, temperature
        ):
            provider_calls.append(provider)
            if provider == "anthropic":
                raise RuntimeError("Anthropic 503")
            return LLMResponse(
                content="hi from openai",
                model_id=model,
                input_tokens=10,
                output_tokens=5,
                provider="openai",
            )

        # Reset the global circuit breaker so prior tests don't leak state.
        from core.llm.circuit_breaker import CircuitBreaker
        import core.llm.circuit_breaker as cb_mod

        with patch.object(cb_mod, "_breaker", CircuitBreaker()):
            with patch.object(LLMClient, "_call_provider", fake_call_provider), \
                 patch("core.llm.cache.get_cached_completion", AsyncMock(return_value=None)), \
                 patch("core.llm.cache.set_cached_completion", AsyncMock()), \
                 patch("core.llm.budget.record_usage_usd", AsyncMock()):
                client = LLMClient(
                    primary_provider="anthropic",
                    primary_model="claude-x",
                    fallback_provider="openai",
                    fallback_model="gpt-x",
                )
                resp = await client.complete(
                    system="s", user="u", mailbox_id=None
                )

        assert resp.provider == "openai"
        assert resp.content == "hi from openai"
        # Must have tried anthropic FIRST, then fallen back to openai.
        assert provider_calls == ["anthropic", "openai"]

    @pytest.mark.asyncio
    async def test_open_primary_breaker_skips_to_fallback_immediately(self):
        """If the breaker is already open on the primary, the client must skip
        the primary call entirely and go straight to the fallback."""
        from core.llm.client import LLMClient, LLMResponse
        from core.llm.circuit_breaker import CircuitBreaker
        import core.llm.circuit_breaker as cb_mod

        provider_calls: list[str] = []

        async def fake_call_provider(
            self, *, provider, model, system, user, max_tokens, temperature
        ):
            provider_calls.append(provider)
            return LLMResponse(
                content="ok",
                model_id=model,
                input_tokens=1,
                output_tokens=1,
                provider=provider,
            )

        # Pre-trip the breaker on anthropic.
        fresh_breaker = CircuitBreaker()
        for _ in range(FAILURE_THRESHOLD):
            fresh_breaker.record_failure("anthropic")
        assert fresh_breaker.is_available("anthropic") is False

        with patch.object(cb_mod, "_breaker", fresh_breaker), \
             patch.object(LLMClient, "_call_provider", fake_call_provider), \
             patch("core.llm.cache.get_cached_completion", AsyncMock(return_value=None)), \
             patch("core.llm.cache.set_cached_completion", AsyncMock()), \
             patch("core.llm.budget.record_usage_usd", AsyncMock()):
            client = LLMClient(
                primary_provider="anthropic",
                primary_model="claude-x",
                fallback_provider="openai",
                fallback_model="gpt-x",
            )
            resp = await client.complete(system="s", user="u", mailbox_id=None)

        assert resp.provider == "openai"
        # Anthropic was skipped entirely.
        assert provider_calls == ["openai"]


# ─────────────────────── Gmail rate limiter ──────────────────────────────


class _FakeAsyncRedis:
    """Minimal async Redis stand-in supporting get / pipeline / incr / expire."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def get(self, key: str):
        v = self.store.get(key)
        if v is None:
            return None
        return str(v)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeAsyncRedis) -> None:
        self.redis = redis
        self._ops: list = []

    def incr(self, key: str):
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int):
        self._ops.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "incr":
                _, key = op
                self.redis.store[key] = self.redis.store.get(key, 0) + 1
                results.append(self.redis.store[key])
            else:
                results.append(True)
        self._ops.clear()
        return results


class TestGmailRateLimiter:
    @pytest.mark.asyncio
    async def test_per_second_bucket_exhaustion_raises_rate_limit_error(self):
        from core.gmail import rate_limiter as rl

        fake = _FakeAsyncRedis()

        with patch.object(rl, "_get_redis", AsyncMock(return_value=fake)):
            # Saturate the per-second bucket at the configured cap (3 here).
            for _ in range(3):
                await rl.check_gmail_rate_limit(
                    "mailbox-A", max_per_second=3, max_per_minute=1000
                )
                await rl.record_gmail_call("mailbox-A")

            # The 4th call must raise.
            with pytest.raises(rl.GmailRateLimitError) as exc:
                await rl.check_gmail_rate_limit(
                    "mailbox-A", max_per_second=3, max_per_minute=1000
                )
            assert exc.value.mailbox_id == "mailbox-A"
            assert exc.value.window == "per_second"

    @pytest.mark.asyncio
    async def test_one_mailbox_exhausting_does_not_starve_another(self):
        """Per-mailbox isolation: keys are namespaced by mailbox_id."""
        from core.gmail import rate_limiter as rl

        fake = _FakeAsyncRedis()

        with patch.object(rl, "_get_redis", AsyncMock(return_value=fake)):
            # Saturate mailbox-A.
            for _ in range(2):
                await rl.check_gmail_rate_limit(
                    "mailbox-A", max_per_second=2, max_per_minute=1000
                )
                await rl.record_gmail_call("mailbox-A")
            with pytest.raises(rl.GmailRateLimitError):
                await rl.check_gmail_rate_limit(
                    "mailbox-A", max_per_second=2, max_per_minute=1000
                )

            # mailbox-B should be unaffected.
            await rl.check_gmail_rate_limit(
                "mailbox-B", max_per_second=2, max_per_minute=1000
            )
            await rl.record_gmail_call("mailbox-B")
            await rl.check_gmail_rate_limit(
                "mailbox-B", max_per_second=2, max_per_minute=1000
            )
            await rl.record_gmail_call("mailbox-B")
            # Now mailbox-B is at its own limit, but only because of its own
            # traffic, not mailbox-A's.
            with pytest.raises(rl.GmailRateLimitError) as exc:
                await rl.check_gmail_rate_limit(
                    "mailbox-B", max_per_second=2, max_per_minute=1000
                )
            assert exc.value.mailbox_id == "mailbox-B"

    @pytest.mark.asyncio
    async def test_under_limit_does_not_raise(self):
        from core.gmail import rate_limiter as rl

        fake = _FakeAsyncRedis()
        with patch.object(rl, "_get_redis", AsyncMock(return_value=fake)):
            # A few calls well under the cap should never raise.
            for _ in range(5):
                await rl.check_gmail_rate_limit(
                    "mailbox-A", max_per_second=25, max_per_minute=500
                )
                await rl.record_gmail_call("mailbox-A")
