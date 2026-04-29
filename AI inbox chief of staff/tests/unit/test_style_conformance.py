"""Style-conformance scorer unit tests.

These cover the deterministic rules in core/style/conformance.py.
The scorer feeds Draft.style_conformance_score and the matching SLO
target in core/slo/targets.py (>= 0.98).
"""

from __future__ import annotations

import pytest

from core.style.conformance import (
    StyleScoreBreakdown,
    score_style,
    score_style_value,
)


# A draft that hits every operator-voice marker and avoids every banned phrase.
GOOD_DRAFT = (
    "Thanks for the context — I would frame this as two buckets: pipeline health "
    "and CRM hygiene. The bottleneck likely sits in the handoff between SDRs and "
    "AEs (a known friction point). My recommendation is to standardize the lead-"
    "qualification framework first; it depends on whether the data integrity "
    "issues are upstream or downstream. Trade-off: a heavier process buys "
    "visibility but slows velocity in the short term, so we should benchmark "
    "before scaling."
)

BAD_DRAFT = (
    "Hey! This is a revolutionary game-changer that is guaranteed to work! "
    "Synergy across the board!"
)

EMPTY_DRAFT = ""


def test_score_good_draft_passes_slo_threshold():
    score = score_style_value(GOOD_DRAFT)
    assert score >= 0.98, f"good draft scored {score}, expected >= 0.98"


def test_score_bad_draft_below_threshold():
    score = score_style_value(BAD_DRAFT)
    assert score < 0.5, f"bad draft scored {score}, expected < 0.5"


def test_score_empty_draft_zero():
    assert score_style_value(EMPTY_DRAFT) == 0.0


def test_breakdown_shape():
    breakdown = score_style(GOOD_DRAFT)
    assert isinstance(breakdown, StyleScoreBreakdown)
    for field in (
        breakdown.no_generic_fluff,
        breakdown.no_absolute_certainty,
        breakdown.has_caveats,
        breakdown.has_operator_syntax,
        breakdown.no_exclamations,
        breakdown.sentence_length,
    ):
        assert 0.0 <= field <= 1.0


def test_exclamation_marks_lower_score():
    plain = "Sounds reasonable. The handoff matters here."
    excl = "Sounds reasonable! The handoff matters here!"
    assert score_style_value(plain) > score_style_value(excl)


def test_generic_fluff_lowers_score():
    """Fluff phrases should drag the score well below the launch SLO (0.98)."""
    fluff = (
        "Let's leverage our world-class synergy to deliver a game-changer. "
        "We will circle back at the end of the day to align on cutting-edge "
        "best-in-class outcomes that move the needle through clear handoffs."
    )
    score = score_style_value(fluff)
    assert score <= 0.5, f"fluff scored {score}, expected <= 0.5"


def test_absolute_certainty_lowers_score():
    absolute = (
        "This solution is guaranteed to work. Always works. Without a doubt "
        "the right call. Definitely will succeed."
    )
    assert score_style_value(absolute) < 0.6


def test_short_text_partial_credit():
    """Short drafts get partial credit on caveat + syntax rules."""
    short = "Sounds good — will do."
    score = score_style_value(short)
    # Short text should not be penalized down to zero just for being short.
    assert score >= 0.5


@pytest.mark.parametrize(
    "draft, threshold",
    [
        (GOOD_DRAFT, 0.98),
        ("Quick reply — confirmed. Will follow up.", 0.50),
    ],
)
def test_known_drafts_meet_minimum(draft: str, threshold: float):
    assert score_style_value(draft) >= threshold
