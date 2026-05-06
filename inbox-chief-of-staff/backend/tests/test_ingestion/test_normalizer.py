import pytest
from app.ingestion.normalizer import NormalizedMessage, validate_normalized_message
from datetime import datetime, timezone


def make_valid_message(**overrides) -> NormalizedMessage:
    defaults = dict(
        message_id="msg_001",
        thread_id="thread_001",
        subject="Test subject",
        sender_email="sender@example.com",
        sender_name="Sender",
        received_at=datetime(2026, 4, 30, tzinfo=timezone.utc),
        body_preview="Short preview.",
        has_attachments=False,
        label_ids=["INBOX"],
    )
    defaults.update(overrides)
    return NormalizedMessage(**defaults)


def test_valid_message_passes_validation() -> None:
    msg = make_valid_message()
    validate_normalized_message(msg)  # should not raise


def test_missing_message_id_raises() -> None:
    msg = make_valid_message(message_id="")
    with pytest.raises(ValueError, match="message_id"):
        validate_normalized_message(msg)


def test_missing_sender_email_raises() -> None:
    msg = make_valid_message(sender_email="")
    with pytest.raises(ValueError, match="sender_email"):
        validate_normalized_message(msg)


def test_body_preview_too_long_raises() -> None:
    msg = make_valid_message(body_preview="x" * 501)
    with pytest.raises(ValueError, match="body_preview"):
        validate_normalized_message(msg)
