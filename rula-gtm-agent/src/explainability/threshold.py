from __future__ import annotations


TIER_DEFINITIONS = {
    "HIGH": {
        "label": "High confidence",
        "range": "75-100",
        "meaning": (
            "Strong first-party commitment language with multi-quarter campaign "
            "plans and no identified blockers. Safe to present to leadership."
        ),
    },
    "MEDIUM": {
        "label": "Medium confidence",
        "range": "40-74",
        "meaning": (
            "Encouraging signals but with caveats — possibly secondhand source, "
            "limited campaign scope, or soft commitment language. Worth pursuing "
            "but flag uncertainties in deal review."
        ),
    },
    "LOW": {
        "label": "Low confidence",
        "range": "0-39",
        "meaning": (
            "Weak or ambiguous evidence. May indicate early-stage interest or "
            "unreliable source. Requires additional evidence before updating "
            "pipeline stage."
        ),
    },
}


def explain_threshold(tier: str, score: int, risk_factors: list[str]) -> str:
    defn = TIER_DEFINITIONS.get(tier, TIER_DEFINITIONS["LOW"])
    risks_str = ", ".join(risk_factors) if risk_factors else "none"
    return (
        f"**{defn['label']}** (score {score}, range {defn['range']})\n\n"
        f"{defn['meaning']}\n\n"
        f"Risk factors present: {risks_str}."
    )


def explain_tier_assignment(score: int, risk_factors: list[str]) -> list[str]:
    reasons: list[str] = []
    if score >= 75:
        reasons.append(f"Score {score} exceeds HIGH threshold (75).")
    elif score >= 40:
        reasons.append(f"Score {score} is within MEDIUM range (40-74).")
    else:
        reasons.append(f"Score {score} falls below MEDIUM threshold (40).")

    for r in risk_factors:
        if r == "SECONDHAND_SOURCE":
            reasons.append("Evidence is secondhand, which limits confidence ceiling.")
        elif r == "SECONDHAND_HIGH_ALERT":
            reasons.append("Tier was capped from HIGH to MEDIUM due to secondhand source.")
        elif "BLOCKER" in r.upper():
            reasons.append(f"Identified blocker: {r}.")
        else:
            reasons.append(f"Risk factor: {r}.")

    return reasons
