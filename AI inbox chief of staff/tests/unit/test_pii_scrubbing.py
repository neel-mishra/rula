"""Tests for PII scrubbing — ensures sensitive data is redacted from logs and payloads."""

from __future__ import annotations

import pytest

from core.security.pii import scrub_string, scrub_dict, scrub_log_event


class TestScrubString:
    def test_email_redacted(self):
        assert scrub_string("Contact neel@example.com for details") == "Contact [EMAIL] for details"

    def test_phone_redacted(self):
        assert "[PHONE]" in scrub_string("Call me at 555-123-4567")

    def test_phone_with_country_code(self):
        assert "[PHONE]" in scrub_string("Call +1 555-123-4567")

    def test_ssn_redacted(self):
        assert "[SSN]" in scrub_string("SSN: 123-45-6789")

    def test_credit_card_redacted(self):
        assert "[CARD]" in scrub_string("Card: 4111 1111 1111 1111")

    def test_oauth_token_redacted(self):
        assert "[OAUTH_TOKEN]" in scrub_string("Token: ya29.a0ARrdaM_XXXXXXXXXXXXXXXXXXXX")

    def test_refresh_token_redacted(self):
        assert "[REFRESH_TOKEN]" in scrub_string("Refresh: 1//0eXXXXXXXXXXXXXXXXXXXXXX")

    def test_bearer_token_redacted(self):
        result = scrub_string("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test.sig")
        assert "eyJ" not in result
        assert "[REDACTED]" in result

    def test_api_key_redacted(self):
        assert "[API_KEY]" in scrub_string("Key: sk-abcdefghijklmnopqrstuvwxyz")

    def test_clean_text_unchanged(self):
        clean = "This is a normal log message about processing email #42"
        assert scrub_string(clean) == clean

    def test_multiple_pii_in_one_string(self):
        text = "User neel@test.com called from 555-123-4567"
        result = scrub_string(text)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "neel@test.com" not in result


class TestScrubDict:
    def test_sensitive_field_fully_redacted(self):
        data = {"username": "neel", "password": "hunter2", "token": "abc123"}
        result = scrub_dict(data)
        assert result["username"] == "neel"
        assert result["password"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"

    def test_nested_dict_scrubbed(self):
        data = {"user": {"email": "neel@test.com", "config": {"api_key": "sk-secret"}}}
        result = scrub_dict(data)
        assert result["user"]["email"] == "[EMAIL]"
        assert result["user"]["config"]["api_key"] == "[REDACTED]"

    def test_list_values_scrubbed(self):
        data = {"recipients": ["alice@test.com", "bob@test.com"]}
        result = scrub_dict(data)
        assert result["recipients"] == ["[EMAIL]", "[EMAIL]"]

    def test_non_string_values_preserved(self):
        data = {"count": 42, "active": True, "score": 0.95}
        assert scrub_dict(data) == data

    def test_max_depth_prevents_infinite_recursion(self):
        # Build deeply nested dict
        data: dict = {}
        current = data
        for i in range(15):
            current[f"level_{i}"] = {}
            current = current[f"level_{i}"]
        current["leaf"] = "value"
        result = scrub_dict(data)
        assert isinstance(result, dict)


class TestScrubLogEvent:
    def test_structlog_processor_interface(self):
        event = {"event": "user.login", "email": "neel@test.com", "access_token": "ya29.xxx"}
        result = scrub_log_event(None, "info", event)
        assert result["email"] == "[EMAIL]"
        assert result["access_token"] == "[REDACTED]"
        assert result["event"] == "user.login"
