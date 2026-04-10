from __future__ import annotations

import logging

from src.schemas.account import EnrichedAccount
from src.schemas.prospecting import ValuePropMatch

logger = logging.getLogger(__name__)

PROP_EXPLANATIONS = {
    "total_cost_of_care": (
        "This employer's profile suggests cost containment is a primary concern. "
        "By leading with total-cost-of-care savings, we align to the buyer's "
        "budget language and demonstrate measurable ROI."
    ),
    "eap_upgrade": (
        "Signals indicate the current EAP may be underperforming or expiring. "
        "Positioning Rula as the modern alternative lets us capture an active "
        "budget cycle with minimal stakeholder friction."
    ),
    "workforce_productivity": (
        "High-turnover or shift-based workforce patterns suggest productivity "
        "loss from untreated behavioral health. This angle quantifies the "
        "absenteeism / presenteeism cost the employer already bears."
    ),
    "employee_access": (
        "Geography, workforce composition, or notes suggest employees may face "
        "access barriers to behavioral health care. Rula's virtual-first model "
        "addresses this gap directly."
    ),
}

VP_TO_PILLAR: dict[str, str] = {
    "total_cost_of_care": "Partner-Ready Infrastructure",
    "eap_upgrade": "Partner-Ready Infrastructure",
    "workforce_productivity": "Progress-Oriented Care",
    "employee_access": "Access Without Delay",
}


def _account_signals(enriched: EnrichedAccount) -> dict[str, list[str]]:
    """Build per-value-prop signal lists from the enriched account context."""
    industry = enriched.account.industry.lower()
    notes = enriched.account.notes.lower()

    vp_signals: dict[str, list[str]] = {vp: [] for vp in PROP_EXPLANATIONS}

    if "health" in industry:
        vp_signals["total_cost_of_care"].append(f"industry = {enriched.account.industry}")
        vp_signals["workforce_productivity"].append(f"industry = {enriched.account.industry}")
    if "university" in industry or "education" in industry:
        vp_signals["eap_upgrade"].append(f"industry = {enriched.account.industry}")
        vp_signals["employee_access"].append(f"industry = {enriched.account.industry}")
    if "senior" in industry or "living" in industry:
        vp_signals["workforce_productivity"].append(f"industry = {enriched.account.industry}")
        vp_signals["total_cost_of_care"].append(f"industry = {enriched.account.industry}")
    if enriched.account.us_employees >= 10000:
        vp_signals["total_cost_of_care"].append(f"size = {enriched.account.us_employees:,} employees")
    if enriched.account.us_employees < 5000:
        vp_signals["employee_access"].append(f"size = {enriched.account.us_employees:,} employees (smaller workforce)")
    if "turnover" in notes or "24/7" in notes:
        vp_signals["workforce_productivity"].append("notes mention turnover / 24-7 ops")
    if "eap" in notes:
        vp_signals["eap_upgrade"].append("notes mention EAP")
    if "limited internet" in notes or "field-based" in notes:
        vp_signals["employee_access"].append("workforce has limited digital access")
    if "merger" in notes or "integrating" in notes:
        vp_signals["total_cost_of_care"].append("recent merger / benefits consolidation")
        vp_signals["eap_upgrade"].append("recent merger / benefits consolidation")
    hp = (enriched.account.health_plan or "").lower()
    if hp and hp not in {"unknown", ""}:
        vp_signals["total_cost_of_care"].append(f"health plan = {enriched.account.health_plan}")

    return vp_signals


def _pillar_tag(value_prop: str) -> str:
    """Map a value prop to a business-DNA messaging pillar."""
    pillar = VP_TO_PILLAR.get(value_prop, "")
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded and reg.bundle.pillars.pillars:
            for name, desc in reg.bundle.pillars.pillars.items():
                if name == pillar:
                    return f"Messaging pillar: {name} — {desc}"
    except Exception:
        pass
    return f"Messaging pillar: {pillar}" if pillar else ""


def explain_value_prop(
    match: ValuePropMatch,
    enriched: EnrichedAccount,
) -> str:
    """v1/v2 explanation (template-based, kept for backward compatibility)."""
    base = PROP_EXPLANATIONS.get(match.value_prop, "Custom match based on account signals.")
    all_signals = _account_signals(enriched)
    prop_signals = all_signals.get(match.value_prop, [])
    signal_str = ", ".join(prop_signals) if prop_signals else "general account profile"
    pillar = _pillar_tag(match.value_prop)
    pillar_line = f"\n\n{pillar}" if pillar else ""
    return f"{base}\n\nSignals: {signal_str}. Match score: {match.score}/100.{pillar_line}"
