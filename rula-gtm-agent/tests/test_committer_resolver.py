"""Committer heuristic + LLM merge behavior."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.agents.verification.committer_resolver import resolve_committer
from src.providers.base import GenerationResponse


def _router_llm_fails() -> MagicMock:
    """Force heuristic path so tests do not depend on API keys or real LLM output."""
    m = MagicMock()
    m.generate.return_value = GenerationResponse(
        text="",
        provider="none",
        model="none",
        prompt_version="v1",
        error="unavailable",
    )
    return m


def test_heuristic_email_from_name_and_title() -> None:
    text = "Email from David Chen (VP, Total Rewards) to AE, February 14: Thanks."
    ce = resolve_committer(text, "", router=_router_llm_fails())
    assert ce.name == "David Chen"
    assert ce.title == "VP, Total Rewards"
    assert ce.source == "heuristic"


def test_heuristic_email_from_name_to_ae() -> None:
    text = (
        "Email from David Chen to AE, February 14: Thanks for the presentation yesterday. "
        "We're excited to move forward."
    )
    ce = resolve_committer(text, "", router=_router_llm_fails())
    assert ce.name == "David Chen"
    assert ce.title is None


def test_heuristic_james_meeting_notes() -> None:
    text = "Excerpt from AE meeting notes, February 10: James mentioned they're interested."
    ce = resolve_committer(text, "", router=_router_llm_fails())
    assert ce.name == "James"


def test_resolve_prefers_llm_when_json_valid() -> None:
    mock_router = MagicMock()
    mock_router.generate.return_value = MagicMock(
        ok=True,
        text='{"name": "Pat Lee", "title": "Director", "rationale": "test"}',
        provider="gemini",
        model="x",
        prompt_version="v1",
        error=None,
    )
    text = "Slack: random text without patterns."
    ce = resolve_committer(text, "", router=mock_router)
    assert ce.name == "Pat Lee"
    assert ce.title == "Director"
    assert ce.source == "llm"
