"""Segment-level override logic and competitor mapping for Stage 4 generation.

Deterministic, config-driven, and separate from LLM prompt text.
Business DNA context may enrich segment labels and wedge descriptions
but never overrides the deterministic segment → VP override table.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.agents.prospecting.value_prop_taxonomy import normalize_industry
from src.schemas.prospecting import ValuePropMatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Segment -> value-prop emphasis override
# ---------------------------------------------------------------------------

SEGMENT_VP_OVERRIDES: dict[str, str] = {
    "health_system": "total_cost_of_care",
    "university": "employee_access",
}

# ---------------------------------------------------------------------------
# Static competitor mapping (by segment)
# ---------------------------------------------------------------------------

SEGMENT_COMPETITORS: dict[str, str] = {
    "health_system": "similar health systems",
    "university": "peer universities",
    "senior_living": "senior living organizations",
    "financial": "financial services firms",
    "transportation": "logistics companies",
    "natural_resources": "field-heavy employers",
    "other": "employers in your segment",
}


# ---------------------------------------------------------------------------
# Wedge derivation (value-prop -> strategic wedge label)
# ---------------------------------------------------------------------------

WEDGE_MAP: dict[str, str] = {
    "eap_upgrade": "EAP underperformance",
    "total_cost_of_care": "rising health costs",
    "employee_access": "geographic access gaps",
    "workforce_productivity": "workforce productivity loss",
}


@dataclass
class SegmentContext:
    """Deterministic segment-level context for prompt variable binding."""
    segment: str
    emphasis_vp: str
    segment_label: str
    similar_competitor: str
    wedge: str


def resolve_segment_context(
    industry_raw: str,
    matches: list[ValuePropMatch],
) -> SegmentContext:
    """Build deterministic segment context from raw industry and match output."""
    segment = normalize_industry(industry_raw)

    if segment in SEGMENT_VP_OVERRIDES:
        emphasis_vp = SEGMENT_VP_OVERRIDES[segment]
    else:
        emphasis_vp = matches[0].value_prop if matches else "employee_access"

    segment_labels = {
        "health_system": "Health System",
        "university": "University",
        "senior_living": "Senior Living",
        "financial": "Financial Services",
        "transportation": "Transportation & Logistics",
        "natural_resources": "Natural Resources",
        "other": "Large Employer",
    }

    return SegmentContext(
        segment=segment,
        emphasis_vp=emphasis_vp,
        segment_label=segment_labels.get(segment, "Large Employer"),
        similar_competitor=SEGMENT_COMPETITORS.get(segment, "employers in your segment"),
        wedge=WEDGE_MAP.get(emphasis_vp, "benefit engagement friction"),
    )
