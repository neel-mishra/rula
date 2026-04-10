"""Tests for HTML helpers used with unsafe_allow_html."""
from __future__ import annotations

from src.ui.components import confidence_pill, risk_chips


def test_risk_chips_escapes_angle_brackets() -> None:
    html_out = risk_chips(['<script>alert(1)</script>'])
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_confidence_pill_escapes_tier() -> None:
    html_out = confidence_pill('HIGH"><img src=x onerror=alert(1)>', 50)
    assert "<img" not in html_out
    assert "&lt;img" in html_out
