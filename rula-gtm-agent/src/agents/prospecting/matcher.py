from __future__ import annotations

from src.agents.prospecting.value_prop_scoring import (
    ScoringResult,
    score_value_props,
)
from src.schemas.account import EnrichedAccount
from src.schemas.prospecting import ValuePropMatch


def match_value_props(enriched: EnrichedAccount) -> list[ValuePropMatch]:
    """Score and rank value props using the v3 config-driven scoring engine."""
    result = score_value_props(enriched)
    return result.matches


def match_value_props_detailed(enriched: EnrichedAccount) -> ScoringResult:
    """Return full scoring result including signal attributions."""
    return score_value_props(enriched)
