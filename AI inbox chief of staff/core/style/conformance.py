"""Deterministic style-conformance scorer.

Scores a generated draft against the writing-style.md policy on
6 measurable rules. Returns a single float in [0, 1] suitable for
persisting to `Draft.style_conformance_score` and for the
`style_conformance` SLO target (>= 0.98).

Rules are intentionally cheap (regex + length stats only) so this
runs inline after every draft generation without LLM cost. The
launch SLO uses a strict threshold; deterministic + fast keeps it
honest.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

# ── Banned-phrase lexicons ─────────────────────────────────────────────────
# Pulled from writing-style.md "Don't" rules + "Avoid generic consultant fluff".

_GENERIC_FLUFF = (
    "revolutionary", "synergy", "synergies", "best-in-class", "world-class",
    "game-changer", "game changing", "cutting-edge", "leverage our",
    "circle back", "deep dive into", "moving forward we will",
    "at the end of the day", "low-hanging fruit",
)

# Absolute-certainty markers without hedge — fails "Don't use absolute certainty".
_ABSOLUTE_CERTAINTY = (
    "guaranteed to", "always works", "never fails", "100% reliable",
    "without a doubt", "definitely will", "certain to succeed",
)

# Hedging / caveat markers — presence increases score per "acknowledges uncertainty".
_CAVEAT_MARKERS = (
    "likely", "depends on", "as a starting point", "i would",
    "if x", "trade-off", "trade-offs", "caveat", "depending on",
    "in many cases", "typically", "tends to", "with the caveat",
    "assumption", "constraint",
)

# Operator-syntax markers — presence increases score per "syntax and sentence mechanics".
_OPERATOR_SYNTAX_PATTERNS = (
    re.compile(r"—"),                           # em dash
    re.compile(r":\s+\w"),                      # colon-introduces-clause
    re.compile(r"\([^)]{2,}\)"),                # parenthetical clarification
    re.compile(r"\"[A-Z][^\"]{2,}\""),           # quoted operating term
)

_EXCLAMATION_RE = re.compile(r"!")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


@dataclass(frozen=True)
class StyleScoreBreakdown:
    """Per-rule sub-scores (each in [0, 1]) and the final aggregate."""
    no_generic_fluff: float
    no_absolute_certainty: float
    has_caveats: float
    has_operator_syntax: float
    no_exclamations: float
    sentence_length: float
    final: float


def score_style(text: str) -> StyleScoreBreakdown:
    """Return a per-rule breakdown + the equal-weight aggregate score."""
    if not text or not text.strip():
        return StyleScoreBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    body = text.strip()
    body_lower = body.lower()

    no_fluff = _no_match_score(body_lower, _GENERIC_FLUFF)
    no_absolute = _no_match_score(body_lower, _ABSOLUTE_CERTAINTY)
    caveats = _has_at_least_one(body_lower, _CAVEAT_MARKERS)
    operator = _operator_syntax_score(body)
    no_excl = _no_exclamation_score(body)
    length = _sentence_length_score(body)

    final = round(
        (no_fluff + no_absolute + caveats + operator + no_excl + length) / 6.0,
        4,
    )
    return StyleScoreBreakdown(
        no_generic_fluff=no_fluff,
        no_absolute_certainty=no_absolute,
        has_caveats=caveats,
        has_operator_syntax=operator,
        no_exclamations=no_excl,
        sentence_length=length,
        final=final,
    )


def score_style_value(text: str) -> float:
    """Convenience: return only the aggregate float."""
    return score_style(text).final


# ── Rule helpers ──────────────────────────────────────────────────────────


def _no_match_score(body_lower: str, banned: tuple[str, ...]) -> float:
    """1.0 if no banned phrase appears; degrades by 0.25 per occurrence (floor 0)."""
    hits = sum(1 for phrase in banned if phrase in body_lower)
    return max(0.0, 1.0 - 0.25 * hits)


def _has_at_least_one(body_lower: str, markers: tuple[str, ...]) -> float:
    """1.0 if any marker present; 0.5 if very short text (< 200 chars); else 0.0."""
    if any(marker in body_lower for marker in markers):
        return 1.0
    # Short replies legitimately lack room for caveats — partial credit.
    return 0.5 if len(body_lower) < 200 else 0.0


def _operator_syntax_score(body: str) -> float:
    """1.0 if any operator-syntax pattern matches; 0.5 for very short text; else 0.0."""
    for pattern in _OPERATOR_SYNTAX_PATTERNS:
        if pattern.search(body):
            return 1.0
    return 0.5 if len(body) < 200 else 0.0


def _no_exclamation_score(body: str) -> float:
    """1.0 if no exclamation marks; degrades by 0.5 per occurrence (floor 0)."""
    hits = len(_EXCLAMATION_RE.findall(body))
    return max(0.0, 1.0 - 0.5 * hits)


def _sentence_length_score(body: str) -> float:
    """
    Operator voice prefers medium-to-long sentences (12–28 words mean).
    Score is 1.0 inside the band; degrades linearly outside.
    """
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(body) if s.strip()]
    if not sentences:
        return 0.0
    word_counts = [len(s.split()) for s in sentences]
    mean_len = statistics.mean(word_counts)
    if 12 <= mean_len <= 28:
        return 1.0
    # Distance from the band, normalized.
    if mean_len < 12:
        return max(0.0, mean_len / 12.0)
    return max(0.0, 1.0 - (mean_len - 28) / 28.0)
