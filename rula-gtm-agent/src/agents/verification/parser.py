from __future__ import annotations

import logging

from src.agents.verification.commitment_extractor import extract_commitments
from src.schemas.map_verification import CampaignCommitment, ParsedEvidence

logger = logging.getLogger(__name__)



def _soft_interest_phrases() -> list[str]:
    """Get soft-interest blocker phrases, enriched from business DNA."""
    base = ["no commitment", "exploring"]
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            for p in reg.bundle.map_semantics.soft_interest_phrases:
                if p.lower() not in base:
                    base.append(p.lower())
    except Exception:
        pass
    return base


def parse_evidence(evidence_id: str, text: str) -> ParsedEvidence:
    lower = text.lower()
    source_directness = "first_party" if "email from" in lower else "ae_reported"
    blockers: list[str] = []
    extraction = extract_commitments(text)
    campaigns = [
        CampaignCommitment(
            campaign_type=c.campaign_type,
            quarter=c.quarter,
            year=c.year,
        )
        for c in extraction.commitments
    ]

    for phrase in _soft_interest_phrases():
        if phrase in lower:
            blockers.append("SOFT_INTEREST_ONLY")
            break
    if "buy-in" in lower:
        blockers.append("NEEDS_INTERNAL_BUY_IN")

    return ParsedEvidence(
        evidence_id=evidence_id,
        source_directness=source_directness,
        campaigns=campaigns,
        total_quarters=len({c.quarter for c in campaigns}),
        commitment_year=extraction.inferred_year,
        commitment_strategy=extraction.strategy,
        commitment_ambiguities=extraction.ambiguities,
        language_excerpt=text[:240],
        blockers=blockers,
    )
