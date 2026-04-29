"""Tests for token budget enforcement logic (unit-level, no Redis required)."""

from __future__ import annotations

import pytest

from core.llm.budget import BudgetExhaustedError, _cents_to_tokens


class TestBudgetConversion:
    def test_cents_to_tokens(self):
        assert _cents_to_tokens(75) == 750_000  # $0.75 = 750k tokens
        assert _cents_to_tokens(100) == 1_000_000
        assert _cents_to_tokens(0) == 0

    def test_budget_exhausted_error_attrs(self):
        err = BudgetExhaustedError("daily_mailbox", 800_000, 750_000)
        assert err.scope == "daily_mailbox"
        assert err.used == 800_000
        assert err.limit == 750_000
        assert "daily_mailbox" in str(err)
        assert "800000" in str(err)
