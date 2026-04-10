"""Config-driven value-prop scoring engine with signal attribution.

Replaces the ad-hoc increments in matcher.py with a structured,
versioned scoring model that emits per-signal evidence for explainability.

Business DNA ICP context (when loaded) enriches anti-ICP penalty checks
but never overrides the deterministic scoring rules in this module.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from src.agents.prospecting.value_prop_taxonomy import (
    PRIORITY_CARRIERS,
    extract_context_signals,
    normalize_health_plan,
    normalize_industry,
)
from src.schemas.account import EnrichedAccount
from src.schemas.prospecting import ValuePropMatch

logger = logging.getLogger(__name__)

VALUE_PROPS = [
    "total_cost_of_care",
    "eap_upgrade",
    "workforce_productivity",
    "employee_access",
]

SCORING_VERSION = "v3.0"

# ---------------------------------------------------------------------------
# Signal attribution record
# ---------------------------------------------------------------------------

@dataclass
class SignalAttribution:
    signal: str
    value_prop: str
    weight: int
    matched_text: str
    source_field: str


# ---------------------------------------------------------------------------
# Scoring config  (weights are point increments, not percentages)
# ---------------------------------------------------------------------------

INDUSTRY_RULES: list[dict] = [
    {"segment": "health_system",   "vp": "total_cost_of_care",    "weight": 30},
    {"segment": "health_system",   "vp": "workforce_productivity", "weight": 20},
    {"segment": "university",      "vp": "eap_upgrade",           "weight": 25},
    {"segment": "university",      "vp": "employee_access",       "weight": 20},
    {"segment": "senior_living",   "vp": "workforce_productivity", "weight": 25},
    {"segment": "senior_living",   "vp": "total_cost_of_care",    "weight": 15},
    {"segment": "financial",       "vp": "total_cost_of_care",    "weight": 15},
    {"segment": "financial",       "vp": "workforce_productivity", "weight": 10},
    {"segment": "transportation",  "vp": "workforce_productivity", "weight": 20},
    {"segment": "transportation",  "vp": "employee_access",       "weight": 15},
    {"segment": "natural_resources", "vp": "employee_access",     "weight": 25},
]

SIZE_BREAKPOINTS = [
    {"min": 15_000, "max": None, "vp": "total_cost_of_care", "weight": 15},
    {"min": 5_000,  "max": 14_999, "vp": "total_cost_of_care", "weight": 8},
    {"min": 0,      "max": 4_999,  "vp": "employee_access",    "weight": 10},
]

PLAN_RULES = [
    {"family_in": PRIORITY_CARRIERS, "vp": "total_cost_of_care", "weight": 10},
]

CONTEXT_BUCKET_WEIGHT: dict[str, dict[str, int]] = {
    "workforce_productivity": {"workforce_productivity": 20},
    "eap_upgrade":           {"eap_upgrade": 25},
    "employee_access":       {"employee_access": 15},
    "total_cost_of_care":    {"total_cost_of_care": 15, "eap_upgrade": 10},
}

SATURATION_CAP = 40
BASE_SCORE = 25
NEGATIVE_PENALTY = 5
CONTRADICTION_PENALTY_STRONG = 8
CONTRADICTION_PENALTY_MILD = 4


# ---------------------------------------------------------------------------
# Interaction-term boosts
# ---------------------------------------------------------------------------

def _interaction_boosts(
    segment: str,
    carrier_family: str,
    context_buckets: set[str],
) -> list[tuple[str, str, int, str]]:
    """Return (signal_name, vp, weight, description) for cross-signal boosts."""
    boosts: list[tuple[str, str, int, str]] = []
    if carrier_family in PRIORITY_CARRIERS and "employee_access" in context_buckets:
        boosts.append((
            "plan_x_access_complaints",
            "employee_access",
            8,
            f"carrier={carrier_family} + access-friction context",
        ))
    if segment == "health_system" and "total_cost_of_care" in context_buckets:
        boosts.append((
            "health_system_x_cost_context",
            "total_cost_of_care",
            6,
            "health-system segment + cost-containment context",
        ))
    return boosts


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

@dataclass
class ScoringResult:
    matches: list[ValuePropMatch]
    attributions: list[SignalAttribution]
    scoring_version: str = SCORING_VERSION


def score_value_props(enriched: EnrichedAccount) -> ScoringResult:
    """Score all value props for an enriched account, with full attribution."""
    scores: dict[str, int] = {vp: BASE_SCORE for vp in VALUE_PROPS}
    attributions: list[SignalAttribution] = []

    segment = normalize_industry(enriched.account.industry)
    _carrier_name, carrier_family = normalize_health_plan(enriched.account.health_plan)
    emps = enriched.account.us_employees

    # --- Industry signals ---
    for rule in INDUSTRY_RULES:
        if rule["segment"] == segment:
            vp, w = rule["vp"], rule["weight"]
            scores[vp] += w
            attributions.append(SignalAttribution(
                signal=f"industry_{segment}",
                value_prop=vp,
                weight=w,
                matched_text=enriched.account.industry,
                source_field="industry",
            ))

    # --- Size signals ---
    for bp in SIZE_BREAKPOINTS:
        lo, hi = bp["min"], bp["max"]
        if emps >= lo and (hi is None or emps <= hi):
            vp, w = bp["vp"], bp["weight"]
            scores[vp] += w
            attributions.append(SignalAttribution(
                signal=f"size_{lo}_{hi or 'plus'}",
                value_prop=vp,
                weight=w,
                matched_text=f"{emps:,} employees",
                source_field="us_employees",
            ))
            break

    # --- Health-plan signals ---
    for rule in PLAN_RULES:
        if carrier_family in rule["family_in"]:
            vp, w = rule["vp"], rule["weight"]
            scores[vp] += w
            attributions.append(SignalAttribution(
                signal=f"plan_{carrier_family}",
                value_prop=vp,
                weight=w,
                matched_text=enriched.account.health_plan or "",
                source_field="health_plan",
            ))

    # --- Context signals (notes) ---
    context_hits = extract_context_signals(enriched.account.notes)
    context_buckets: set[str] = set()
    for hit in context_hits:
        bucket = hit["bucket"]
        polarity = hit["polarity"]
        if polarity == "risk":
            for vp in scores:
                scores[vp] -= NEGATIVE_PENALTY
            attributions.append(SignalAttribution(
                signal=f"negative_{hit['phrase']}",
                value_prop="_all",
                weight=-NEGATIVE_PENALTY,
                matched_text=hit["phrase"],
                source_field="notes",
            ))
        elif polarity == "contradiction":
            for vp in scores:
                scores[vp] -= CONTRADICTION_PENALTY_MILD
            attributions.append(SignalAttribution(
                signal=f"contradiction_{hit['phrase']}",
                value_prop="_all",
                weight=-CONTRADICTION_PENALTY_MILD,
                matched_text=hit["phrase"],
                source_field="notes",
            ))
        else:
            context_buckets.add(bucket)
            bucket_weights = CONTEXT_BUCKET_WEIGHT.get(bucket, {})
            for vp, w in bucket_weights.items():
                scores[vp] += w
                attributions.append(SignalAttribution(
                    signal=f"context_{hit['phrase']}",
                    value_prop=vp,
                    weight=w,
                    matched_text=hit["phrase"],
                    source_field="notes",
                ))

    # --- Interaction-term boosts ---
    for sig_name, vp, w, desc in _interaction_boosts(segment, carrier_family, context_buckets):
        scores[vp] += w
        attributions.append(SignalAttribution(
            signal=sig_name,
            value_prop=vp,
            weight=w,
            matched_text=desc,
            source_field="interaction",
        ))

    # --- Anti-ICP penalty from business DNA context ---
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded and reg.bundle.icp.anti_icp_signals:
            notes_lower = enriched.account.notes.lower()
            for signal in reg.bundle.icp.anti_icp_signals:
                trigger = signal.lower().split(".")[0][:40]
                if trigger and any(word in notes_lower for word in trigger.split() if len(word) > 4):
                    for vp in scores:
                        scores[vp] -= NEGATIVE_PENALTY
                    attributions.append(SignalAttribution(
                        signal=f"anti_icp_{trigger[:20]}",
                        value_prop="_all",
                        weight=-NEGATIVE_PENALTY,
                        matched_text=signal[:60],
                        source_field="business_dna:icp",
                    ))
                    break
    except Exception:
        pass

    # --- Saturation caps ---
    increment_by_vp: dict[str, int] = {}
    for attr in attributions:
        if attr.weight > 0 and attr.value_prop != "_all":
            increment_by_vp[attr.value_prop] = increment_by_vp.get(attr.value_prop, 0) + attr.weight
    for vp, total_inc in increment_by_vp.items():
        if total_inc > SATURATION_CAP:
            excess = total_inc - SATURATION_CAP
            scores[vp] -= excess

    # --- Clamp and build matches ---
    final = {vp: max(0, min(100, s)) for vp, s in scores.items()}

    sorted_vps = sorted(
        final.items(),
        key=lambda x: (-x[1], VALUE_PROPS.index(x[0])),
    )

    matches = []
    for vp, score in sorted_vps:
        vp_attrs = [a for a in attributions if a.value_prop in (vp, "_all")]
        signal_parts = []
        for a in vp_attrs:
            if a.weight > 0:
                signal_parts.append(f"{a.signal} (+{a.weight})")
            else:
                signal_parts.append(f"{a.signal} ({a.weight})")
        reasoning = (
            f"{vp.replace('_', ' ')}; "
            f"score={score}; "
            f"signals: {', '.join(signal_parts) if signal_parts else 'baseline only'}; "
            f"industry={enriched.account.industry}, size={enriched.account.us_employees:,}"
        )
        matches.append(ValuePropMatch(value_prop=vp, score=score, reasoning=reasoning))

    return ScoringResult(
        matches=matches,
        attributions=attributions,
        scoring_version=SCORING_VERSION,
    )
