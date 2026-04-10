from __future__ import annotations

from src.validators.response_validator import (
    validate_email_json,
    validate_email_semantic,
    validate_questions_json,
)


def test_valid_email_json() -> None:
    raw = '{"subject_line": "Hi", "body": "This is a body paragraph about something.", "cta": "Call me"}'
    result = validate_email_json(raw)
    assert result.valid


def test_missing_body() -> None:
    raw = '{"subject_line": "Hi"}'
    result = validate_email_json(raw)
    assert not result.valid
    assert any("body" in i for i in result.issues)


def test_invalid_json() -> None:
    result = validate_email_json("not json at all")
    assert not result.valid


def test_fenced_json() -> None:
    raw = '```json\n{"subject_line": "X", "body": "A good body text for testing purposes."}\n```'
    result = validate_email_json(raw)
    assert result.valid


def test_questions_valid() -> None:
    raw = '["What is A?", "What is B?", "What is C?"]'
    result = validate_questions_json(raw)
    assert result.valid


def test_questions_no_question_mark() -> None:
    raw = '["statement one", "statement two"]'
    result = validate_questions_json(raw)
    assert not result.valid


def test_semantic_company_check() -> None:
    data = {"subject_line": "Hello", "body": "Some body text.\n\nMore details."}
    result = validate_email_semantic(data, "TestCo")
    assert not result.valid
    assert any("TestCo" in i for i in result.issues)


def test_semantic_exciting_banned() -> None:
    data = {"subject_line": "Exciting news", "body": "This is exciting!\n\nMore stuff."}
    result = validate_email_semantic(data, "exciting")
    assert any("exciting" in i.lower() for i in result.issues)
