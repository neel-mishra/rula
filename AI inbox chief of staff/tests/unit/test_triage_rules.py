"""Unit tests for deterministic triage rule engine."""

from __future__ import annotations

import pytest

from subagents.triage import (
    AlwaysInboxRule,
    NewsletterRule,
    DirectReplyRule,
    run_rule_engine,
)
from core.models.triage import TriageOutcome


class TestAlwaysInboxRule:
    rule = AlwaysInboxRule()

    def _memories_with_always_inbox(self, targets: list[str]) -> list[dict]:
        return [
            {
                "memory_type": "policy",
                "content": "Always keep in inbox",
                "structured_data": {"rule": "always_inbox", "targets": targets},
            }
        ]

    def test_sender_in_always_inbox_list(self):
        features = {"from_address": "boss@company.com", "from_domain": "company.com"}
        memories = self._memories_with_always_inbox(["boss@company.com"])
        result = self.rule.evaluate(features, memories)
        assert result is not None
        outcome, conf, name = result
        assert outcome == TriageOutcome.PROTECTED
        assert conf == 1.0
        assert name == "always_inbox"

    def test_domain_in_always_inbox_list(self):
        features = {"from_address": "anyone@vip.com", "from_domain": "vip.com"}
        memories = self._memories_with_always_inbox(["vip.com"])
        result = self.rule.evaluate(features, memories)
        assert result is not None
        assert result[0] == TriageOutcome.PROTECTED

    def test_unlisted_sender_returns_none(self):
        features = {"from_address": "unknown@spam.com", "from_domain": "spam.com"}
        memories = self._memories_with_always_inbox(["boss@company.com"])
        result = self.rule.evaluate(features, memories)
        assert result is None

    def test_no_memories_returns_none(self):
        features = {"from_address": "anyone@any.com", "from_domain": "any.com"}
        result = self.rule.evaluate(features, [])
        assert result is None


class TestNewsletterRule:
    rule = NewsletterRule()

    def test_newsletter_goes_to_brief(self):
        features = {"is_newsletter": True, "sender_vip": False}
        result = self.rule.evaluate(features, [])
        assert result is not None
        assert result[0] == TriageOutcome.BRIEF_ONLY
        assert result[1] >= 0.9

    def test_newsletter_from_vip_not_briefed(self):
        features = {"is_newsletter": True, "sender_vip": True}
        result = self.rule.evaluate(features, [])
        assert result is None

    def test_non_newsletter_returns_none(self):
        features = {"is_newsletter": False, "sender_vip": False}
        result = self.rule.evaluate(features, [])
        assert result is None


class TestDirectReplyRule:
    rule = DirectReplyRule()

    def test_direct_reply_kept_in_inbox(self):
        features = {"is_reply": True, "is_direct_to_user": True}
        result = self.rule.evaluate(features, [])
        assert result is not None
        assert result[0] == TriageOutcome.INBOX_KEEP

    def test_reply_not_direct_no_match(self):
        features = {"is_reply": True, "is_direct_to_user": False}
        result = self.rule.evaluate(features, [])
        assert result is None

    def test_non_reply_returns_none(self):
        features = {"is_reply": False, "is_direct_to_user": True}
        result = self.rule.evaluate(features, [])
        assert result is None


class TestRuleEnginePrecedence:
    """AlwaysInbox must beat newsletter rule."""

    def test_always_inbox_beats_newsletter(self):
        features = {
            "from_address": "vip@list.com",
            "from_domain": "list.com",
            "is_newsletter": True,
            "sender_vip": False,
        }
        memories = [
            {
                "memory_type": "policy",
                "content": "Always keep in inbox",
                "structured_data": {"rule": "always_inbox", "targets": ["list.com"]},
            }
        ]
        outcome, conf, rule_name = run_rule_engine(features, memories)
        assert outcome == TriageOutcome.PROTECTED
        assert rule_name == "always_inbox"

    def test_no_rule_match_returns_none(self):
        features = {
            "from_address": "regular@company.com",
            "from_domain": "company.com",
            "is_newsletter": False,
            "is_reply": False,
        }
        result = run_rule_engine(features, [])
        assert result is None
