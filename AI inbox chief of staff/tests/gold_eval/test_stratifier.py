"""Stratifier unit tests — one happy case per stratum."""

from __future__ import annotations

from core.gold_eval.stratifier import classify_stratum
from core.models.gold_sample import GoldStratum


def _email(headers: list[tuple[str, str]], body: str = "", parts: list | None = None) -> dict:
    return {
        "payload": {"headers": [{"name": k, "value": v} for k, v in headers], "parts": parts or []},
        "snippet": body,
    }


def test_newsletter_via_list_unsubscribe():
    email = _email(
        [
            ("From", "Updates <updates@news.example.com>"),
            ("To", "user@example.com"),
            ("List-Unsubscribe", "<https://news.example.com/unsub>"),
        ]
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.NEWSLETTER


def test_calendar_via_attachment():
    email = _email(
        [("From", "boss@example.com"), ("To", "user@example.com")],
        parts=[{"mimeType": "text/calendar", "filename": "invite.ics"}],
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.CALENDAR


def test_calendar_via_domain():
    email = _email(
        [
            ("From", "Google Calendar <noreply@calendar.google.com>"),
            ("To", "user@example.com"),
        ]
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.CALENDAR


def test_direct_reply():
    email = _email(
        [
            ("From", "colleague@example.com"),
            ("To", "user@example.com"),
            ("In-Reply-To", "<prev@example.com>"),
        ],
        body="Sounds good.",
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.DIRECT_REPLY


def test_update_transactional():
    email = _email(
        [
            ("From", "noreply@stripe.example.com"),
            ("To", "user@example.com"),
        ],
        body="Your receipt for order #1234.",
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.UPDATE


def test_action_required_via_question():
    email = _email(
        [
            ("From", "client@partner.example.com"),
            ("To", "user@example.com"),
        ],
        body="Could you review the attached spec by Friday?",
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.ACTION_REQUIRED


def test_ambiguous_default():
    email = _email(
        [
            ("From", "stranger@example.com"),
            ("To", "user@example.com"),
        ],
        body="hi",
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.AMBIGUOUS


def test_newsletter_outranks_action_required():
    """Newsletter heuristic precedes the question-imperative heuristic."""
    email = _email(
        [
            ("From", "news@example.com"),
            ("To", "user@example.com"),
            ("List-Unsubscribe", "<https://example.com/unsub>"),
        ],
        body="Could you click here please?",
    )
    assert classify_stratum(email, user_email="user@example.com") == GoldStratum.NEWSLETTER
