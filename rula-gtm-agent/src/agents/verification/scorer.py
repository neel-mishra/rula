from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.schemas.map_verification import ParsedEvidence

logger = logging.getLogger(__name__)

SCORING_VERSION = "map_v1.0"


def _firm_commitment_phrases() -> list[str]:
    """Firm-commitment language patterns, enriched from business DNA."""
    base = ["excited to move forward"]
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            for p in reg.bundle.map_semantics.firm_commitment_phrases:
                if p.lower() not in base:
                    base.append(p.lower())
    except Exception:
        pass
    return base


@dataclass
class ScoreAttribution:
    signal: str
    points: int
    matched_text: str
    source_field: str


@dataclass
class ScoreBreakdown:
    base: int
    source_directness: int
    campaign_count: int
    quarter_span: int
    blocker_penalty: int
    language_positive: int
    language_negative: int
    attributions: list[ScoreAttribution] = field(default_factory=list)
    scoring_version: str = SCORING_VERSION


def score_commitment(parsed: ParsedEvidence) -> tuple[int, str, list[str]]:
    """Score commitment evidence. Returns (score, tier, risks).

    Backward-compatible 3-tuple return; use score_commitment_detailed
    for the full breakdown.
    """
    result = score_commitment_detailed(parsed)
    return result.score, result.tier, result.risks


@dataclass
class DetailedScoreResult:
    score: int
    tier: str
    risks: list[str]
    breakdown: ScoreBreakdown


def score_commitment_detailed(parsed: ParsedEvidence) -> DetailedScoreResult:
    """Score with full attribution breakdown for transparency."""
    base = 20
    risks: list[str] = []
    attributions: list[ScoreAttribution] = []

    source_pts = 0
    if parsed.source_directness == "first_party":
        source_pts = 35
        attributions.append(ScoreAttribution(
            signal="first_party_source", points=35,
            matched_text=parsed.source_directness, source_field="source_directness",
        ))
    else:
        risks.append("SECONDHAND_SOURCE")
        attributions.append(ScoreAttribution(
            signal="secondhand_source", points=0,
            matched_text=parsed.source_directness, source_field="source_directness",
        ))

    campaign_pts = min(30, len(parsed.campaigns) * 10)
    if campaign_pts:
        attributions.append(ScoreAttribution(
            signal="campaign_count", points=campaign_pts,
            matched_text=f"{len(parsed.campaigns)} campaign(s)", source_field="campaigns",
        ))

    quarter_pts = min(15, parsed.total_quarters * 5)
    if quarter_pts:
        attributions.append(ScoreAttribution(
            signal="quarter_span", points=quarter_pts,
            matched_text=f"{parsed.total_quarters} quarter(s)", source_field="total_quarters",
        ))

    blocker_pts = 0
    if parsed.blockers:
        blocker_pts = -25
        risks.extend(parsed.blockers)
        attributions.append(ScoreAttribution(
            signal="blockers", points=blocker_pts,
            matched_text=", ".join(parsed.blockers), source_field="blockers",
        ))

    lang_pos = 0
    lang_neg = 0
    excerpt_lower = parsed.language_excerpt.lower()
    for phrase in _firm_commitment_phrases():
        if phrase in excerpt_lower:
            lang_pos = 10
            attributions.append(ScoreAttribution(
                signal="positive_language", points=10,
                matched_text=phrase, source_field="language_excerpt",
            ))
            break
    if "exploring" in excerpt_lower and lang_pos == 0:
        lang_neg = -10
        attributions.append(ScoreAttribution(
            signal="exploratory_language", points=-10,
            matched_text="exploring", source_field="language_excerpt",
        ))

    raw = base + source_pts + campaign_pts + quarter_pts + blocker_pts + lang_pos + lang_neg
    score = max(0, min(100, raw))
    tier = "HIGH" if score >= 75 else "MEDIUM" if score >= 40 else "LOW"

    breakdown = ScoreBreakdown(
        base=base,
        source_directness=source_pts,
        campaign_count=campaign_pts,
        quarter_span=quarter_pts,
        blocker_penalty=blocker_pts,
        language_positive=lang_pos,
        language_negative=lang_neg,
        attributions=attributions,
    )

    return DetailedScoreResult(
        score=score, tier=tier, risks=sorted(set(risks)), breakdown=breakdown,
    )
