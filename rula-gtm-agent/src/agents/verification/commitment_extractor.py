from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExtractedCommitment:
    campaign_type: str
    quarter: str
    year: int


@dataclass
class CommitmentExtractionResult:
    commitments: list[ExtractedCommitment] = field(default_factory=list)
    inferred_year: int | None = None
    strategy: str = "none"
    ambiguities: list[str] = field(default_factory=list)


_CAMPAIGN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("launch_email", re.compile(r"\blaunch(?:\s+\w+){0,2}\s+email\b")),
    ("benefits_insert", re.compile(r"\bbenefits?\s+insert\b")),
    ("manager_toolkit", re.compile(r"\bmanager(?:\s+\w+){0,2}\s+toolkit\b")),
    ("email_blast", re.compile(r"\bemail(?:\s+|-)?blast\b")),
    ("posters", re.compile(r"\bposters?\b")),
]

_QUARTER_RE = re.compile(r"\bq([1-4])(?:\s*(?:-|/)?\s*(20\d{2}))?\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_FULL_YEAR_RE = re.compile(r"\bquarterly\s+campaigns?\s+for\s+the\s+full\s+year\b")

_MONTH_TO_QUARTER = {
    "january": "Q1",
    "february": "Q1",
    "march": "Q1",
    "april": "Q2",
    "may": "Q2",
    "june": "Q2",
    "july": "Q3",
    "august": "Q3",
    "september": "Q3",
    "october": "Q4",
    "november": "Q4",
    "december": "Q4",
}


def _infer_default_year(text: str) -> int:
    year_match = _YEAR_RE.search(text)
    if year_match:
        return int(year_match.group(1))
    # If month/date exists without a year, default to current year.
    for month in _MONTH_TO_QUARTER:
        if month in text:
            return dt.datetime.now().year
    return dt.datetime.now().year


def _extract_campaign_mentions(text: str) -> list[tuple[str, int, int]]:
    mentions: list[tuple[str, int, int]] = []
    for campaign_type, pattern in _CAMPAIGN_PATTERNS:
        for m in pattern.finditer(text):
            mentions.append((campaign_type, m.start(), m.end()))
    mentions.sort(key=lambda x: x[1])
    return mentions


def _extract_time_mentions(text: str, default_year: int) -> list[tuple[str, int, int, int]]:
    """Return (quarter, year, start, end)."""
    times: list[tuple[str, int, int, int]] = []

    for m in _QUARTER_RE.finditer(text):
        quarter = f"Q{m.group(1)}".upper()
        year = int(m.group(2)) if m.group(2) else default_year
        times.append((quarter, year, m.start(), m.end()))

    for month, quarter in _MONTH_TO_QUARTER.items():
        for m in re.finditer(rf"\b{month}\b", text):
            times.append((quarter, default_year, m.start(), m.end()))

    times.sort(key=lambda x: x[2])
    return times


def _pair_by_nearest(
    campaign_mentions: list[tuple[str, int, int]],
    time_mentions: list[tuple[str, int, int, int]],
) -> list[ExtractedCommitment]:
    commitments: list[ExtractedCommitment] = []
    for c_type, c_start, c_end in campaign_mentions:
        if not time_mentions:
            continue

        # Prefer the nearest time marker that appears after the campaign mention.
        forward = [t for t in time_mentions if t[2] >= c_end]
        if forward:
            nearest = min(forward, key=lambda t: t[2] - c_end)
        else:
            nearest = min(
                time_mentions,
                key=lambda t: min(abs(c_start - t[2]), abs(c_end - t[3])),
            )
        commitments.append(
            ExtractedCommitment(
                campaign_type=c_type,
                quarter=nearest[0],
                year=nearest[1],
            )
        )
    return commitments


def extract_commitments(text: str) -> CommitmentExtractionResult:
    lower = (text or "").lower()
    default_year = _infer_default_year(lower)
    result = CommitmentExtractionResult(inferred_year=default_year)

    # Pattern: broad commitment for full year.
    if _FULL_YEAR_RE.search(lower):
        result.strategy = "full_year_pattern"
        result.commitments = [
            ExtractedCommitment(campaign_type="quarterly_campaign", quarter=q, year=default_year)
            for q in ("Q1", "Q2", "Q3", "Q4")
        ]
        return result

    campaigns = _extract_campaign_mentions(lower)
    times = _extract_time_mentions(lower, default_year)
    paired = _pair_by_nearest(campaigns, times)

    # De-duplicate exact tuples while preserving order.
    seen: set[tuple[str, str, int]] = set()
    deduped: list[ExtractedCommitment] = []
    for item in paired:
        key = (item.campaign_type, item.quarter, item.year)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if campaigns and not times:
        result.ambiguities.append("campaign_mentions_found_without_time_markers")
    if len(campaigns) > 1 and len(times) == 1:
        result.ambiguities.append("multiple_campaigns_single_time_marker")

    result.strategy = "nearest_pairing"
    result.commitments = deduped
    return result
