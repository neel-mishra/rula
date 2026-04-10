"""Tests for MAP 3-slide navigation model.

Validates slide state helpers, navigation guards, and footer nav gating
without requiring a live Streamlit server — mirrors test_prospecting_slide_flow_v4.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _FakeSessionState(dict):
    pass


@pytest.fixture()
def fake_state():
    state = _FakeSessionState()
    with patch("app.st") as mock_st:
        mock_st.session_state = state
        mock_st.rerun = MagicMock()
        yield state, mock_st


class TestMapSlideStateHelpers:
    def test_default_slide_is_1(self, fake_state):
        state, _ = fake_state
        from app import _get_current_map_slide
        assert _get_current_map_slide() == 1

    def test_get_current_map_slide_reads_state(self, fake_state):
        state, _ = fake_state
        state["map_slide"] = 2
        from app import _get_current_map_slide
        assert _get_current_map_slide() == 2

    def test_can_go_next_from_map_slide1_false_when_no_results(self, fake_state):
        state, _ = fake_state
        from app import _can_go_next_from_map_slide1
        assert _can_go_next_from_map_slide1() is False

    def test_can_go_next_from_map_slide1_true_with_bulk_summary(self, fake_state):
        state, _ = fake_state
        state["last_map_bulk_summary"] = "mock_summary"
        from app import _can_go_next_from_map_slide1
        assert _can_go_next_from_map_slide1() is True

    def test_can_go_next_from_map_slide1_true_with_single_result(self, fake_state):
        state, _ = fake_state
        state["last_map_result"] = {"evidence_id": "A"}
        from app import _can_go_next_from_map_slide1
        assert _can_go_next_from_map_slide1() is True

    def test_can_go_next_from_map_slide2_mirrors_slide1(self, fake_state):
        state, _ = fake_state
        from app import _can_go_next_from_map_slide2
        assert _can_go_next_from_map_slide2() is False
        state["last_map_result"] = {"evidence_id": "X"}
        assert _can_go_next_from_map_slide2() is True


class TestMapGoToSlide:
    def test_go_to_map_slide_sets_state(self, fake_state):
        state, mock_st = fake_state
        from app import _go_to_map_slide
        _go_to_map_slide(2)
        assert state["map_slide"] == 2
        mock_st.rerun.assert_called_once()

    def test_go_to_map_slide_ignores_out_of_range(self, fake_state):
        state, mock_st = fake_state
        state["map_slide"] = 1
        from app import _go_to_map_slide
        _go_to_map_slide(0)
        assert state["map_slide"] == 1
        _go_to_map_slide(4)
        assert state["map_slide"] == 1
        mock_st.rerun.assert_not_called()


class TestMapStatePersistence:
    def test_navigation_preserves_map_keys(self, fake_state):
        state, _ = fake_state
        state["last_map_bulk_summary"] = "mock"
        state["last_map_result"] = {"evidence_id": "A"}
        state["active_map_evidence_expander"] = "B"
        from app import _go_to_map_slide
        _go_to_map_slide(2)
        assert state["last_map_bulk_summary"] == "mock"
        assert state["last_map_result"] == {"evidence_id": "A"}
        assert state["active_map_evidence_expander"] == "B"
