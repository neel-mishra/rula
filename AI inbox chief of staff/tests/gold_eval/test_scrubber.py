"""Scrubber unit tests — must-pass cases."""

from __future__ import annotations

import pytest

from core.gold_eval.scrubber import scrub_email_for_gold


def test_signature_truncation():
    body = "Body of the email.\n\n-- \nNeel\nCEO\nneel@example.com"
    out = scrub_email_for_gold(
        {"body_text": body, "from_name": "Neel"}, mailbox_salt="salt-1"
    )
    assert "CEO" not in out["body_text"]
    assert "Body of the email." in out["body_text"]


def test_quoted_chain_truncation():
    body = "Sounds good.\n\nOn Tue, Apr 1, 2026 at 10:00 PM Bob <bob@example.com> wrote:\n> hey"
    out = scrub_email_for_gold(
        {"body_text": body, "from_name": "Alice"}, mailbox_salt="salt-1"
    )
    assert "Sounds good" in out["body_text"]
    assert "hey" not in out["body_text"]


def test_url_token_strip():
    body = "Check https://example.com/page?utm_source=newsletter&keep=1&token=abc123"
    out = scrub_email_for_gold(
        {"body_text": body, "from_name": "Marketing"}, mailbox_salt="salt-1"
    )
    assert "utm_source" not in out["body_text"]
    assert "token=" not in out["body_text"]
    assert "keep=1" in out["body_text"]


def test_name_hash_deterministic_per_salt():
    a = scrub_email_for_gold({"from_name": "Neel"}, mailbox_salt="salt-A")
    b = scrub_email_for_gold({"from_name": "Neel"}, mailbox_salt="salt-A")
    c = scrub_email_for_gold({"from_name": "Neel"}, mailbox_salt="salt-B")
    assert a["from_name"] == b["from_name"]
    assert a["from_name"] != c["from_name"]
    assert a["from_name"].startswith("Person_")


def test_pii_in_body_gets_scrubbed():
    body = "Reach me at neel@example.com or 555-123-4567."
    out = scrub_email_for_gold(
        {"body_text": body, "from_name": "Neel"}, mailbox_salt="salt-1"
    )
    assert "neel@example.com" not in out["body_text"]
    assert "555-123-4567" not in out["body_text"]


def test_attachment_extracts_scrubbed():
    email = {
        "from_name": "Neel",
        "attachment_extracts": [
            {"filename": "contract.pdf", "text": "Signed by neel@example.com"},
        ],
    }
    out = scrub_email_for_gold(email, mailbox_salt="salt-1")
    assert "neel@example.com" not in out["attachment_extracts"][0]["text"]


def test_missing_salt_raises():
    with pytest.raises(ValueError):
        scrub_email_for_gold({"from_name": "Neel"}, mailbox_salt="")
