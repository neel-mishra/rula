"""Unit tests for USD cost computation."""

from __future__ import annotations

import pytest

from core.llm.budget import PRICING_USD_PER_1K, _DEFAULT_PRICE, compute_cost_usd


class TestComputeCostUsd:
    def test_known_model_claude_opus(self):
        # 1000 in + 1000 out at (0.015, 0.075) per 1k → 0.090
        cost = compute_cost_usd("claude-opus-4-7", 1000, 1000)
        assert cost == pytest.approx(0.090)

    def test_known_model_haiku(self):
        cost = compute_cost_usd("claude-haiku-4-5", 500, 500)
        # 0.5 * 0.001 + 0.5 * 0.005 = 0.0005 + 0.0025 = 0.003
        assert cost == pytest.approx(0.003)

    def test_embedding_model_output_tokens_ignored(self):
        cost = compute_cost_usd("text-embedding-3-small", 10_000, 9999)
        # 10 * 0.00002 + anything * 0 = 0.0002
        assert cost == pytest.approx(0.0002)

    def test_unknown_model_falls_back_to_default(self):
        cost = compute_cost_usd("mystery-model-xyz", 1000, 1000)
        price_in, price_out = _DEFAULT_PRICE
        assert cost == pytest.approx(price_in + price_out)

    def test_zero_tokens_zero_cost(self):
        assert compute_cost_usd("claude-opus-4-7", 0, 0) == 0.0

    def test_scales_linearly(self):
        a = compute_cost_usd("gpt-4o", 100, 200)
        b = compute_cost_usd("gpt-4o", 1000, 2000)
        assert b == pytest.approx(a * 10)

    def test_all_registered_models_have_non_negative_prices(self):
        for model, (p_in, p_out) in PRICING_USD_PER_1K.items():
            assert p_in >= 0, model
            assert p_out >= 0, model
