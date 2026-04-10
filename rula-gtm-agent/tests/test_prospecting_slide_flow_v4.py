"""Tests for v4 3-slide navigation model.

Validates slide state helpers, navigation guards, and footer nav gating
without requiring a live Streamlit server.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _FakeSessionState(dict):
    """Minimal dict-like that mimics st.session_state for unit testing."""
    pass


@pytest.fixture()
def fake_state():
    """Provide a clean fake session_state and patch it into the app module."""
    state = _FakeSessionState()
    with patch("app.st") as mock_st:
        mock_st.session_state = state
        mock_st.rerun = MagicMock()
        yield state, mock_st


class TestSlideStateHelpers:
    def test_default_slide_is_1(self, fake_state):
        state, _ = fake_state
        from app import _get_current_slide
        assert _get_current_slide() == 1

    def test_get_current_slide_reads_state(self, fake_state):
        state, _ = fake_state
        state["prospecting_slide"] = 2
        from app import _get_current_slide
        assert _get_current_slide() == 2

    def test_can_go_next_from_slide1_false_when_no_summary(self, fake_state):
        state, _ = fake_state
        from app import _can_go_next_from_slide1
        assert _can_go_next_from_slide1() is False

    def test_can_go_next_from_slide1_true_when_summary_exists(self, fake_state):
        state, _ = fake_state
        state["last_bulk_summary"] = "mock_summary"
        from app import _can_go_next_from_slide1
        assert _can_go_next_from_slide1() is True

    def test_can_go_next_from_slide2_mirrors_summary(self, fake_state):
        state, _ = fake_state
        from app import _can_go_next_from_slide2
        assert _can_go_next_from_slide2() is False
        state["last_bulk_summary"] = "mock"
        assert _can_go_next_from_slide2() is True


class TestGoToSlide:
    def test_go_to_slide_sets_state(self, fake_state):
        state, mock_st = fake_state
        from app import _go_to_slide
        _go_to_slide(2)
        assert state["prospecting_slide"] == 2
        mock_st.rerun.assert_called_once()

    def test_go_to_slide_ignores_out_of_range(self, fake_state):
        state, mock_st = fake_state
        state["prospecting_slide"] = 1
        from app import _go_to_slide
        _go_to_slide(0)
        assert state["prospecting_slide"] == 1
        _go_to_slide(4)
        assert state["prospecting_slide"] == 1
        mock_st.rerun.assert_not_called()


class TestStatePersistenceAcrossSlides:
    def test_navigation_preserves_existing_keys(self, fake_state):
        state, _ = fake_state
        state["edited_accounts"] = {1, 2}
        state["last_bulk_summary"] = "mock"
        state["active_account_expander"] = 1
        from app import _go_to_slide
        _go_to_slide(2)
        assert state["edited_accounts"] == {1, 2}
        assert state["last_bulk_summary"] == "mock"
        assert state["active_account_expander"] == 1
