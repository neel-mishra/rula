"""Unit tests for Gmail OAuth — validates no gmail.send scope is ever requested."""

from __future__ import annotations

import pytest


class TestGmailScopeGuardrail:
    def test_no_send_scope_in_required_scopes(self):
        """CRITICAL: gmail.send must never appear in configured scopes."""
        from core.gmail.auth import _REQUIRED_SCOPES
        for scope in _REQUIRED_SCOPES:
            assert "gmail.send" not in scope, (
                f"gmail.send scope found in required scopes: {scope}. "
                "Auto-send capability is explicitly forbidden."
            )

    def test_required_scopes_are_minimal(self):
        from core.gmail.auth import _REQUIRED_SCOPES
        allowed = {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.labels",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.compose",
        }
        for scope in _REQUIRED_SCOPES:
            assert scope in allowed, f"Unexpected scope in OAuth config: {scope}"

    def test_gmail_compose_present(self):
        """Draft writing requires compose scope."""
        from core.gmail.auth import _REQUIRED_SCOPES
        assert "https://www.googleapis.com/auth/gmail.compose" in _REQUIRED_SCOPES

    def test_gmail_readonly_present(self):
        from core.gmail.auth import _REQUIRED_SCOPES
        assert "https://www.googleapis.com/auth/gmail.readonly" in _REQUIRED_SCOPES
