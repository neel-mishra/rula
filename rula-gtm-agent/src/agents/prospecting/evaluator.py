from __future__ import annotations

from src.schemas.account import EnrichedAccount
from src.schemas.prospecting import OutreachEmail, ValuePropMatch


def evaluate_output(
    enriched: EnrichedAccount,
    email: OutreachEmail,
    matches: list[ValuePropMatch] | None = None,
) -> tuple[float, bool, list[str]]:
    score = 2.5
    flags: list[str] = []

    # --- positive signals (account quality + email quality) ---
    if enriched.icp_fit_score >= 80:
        score += 0.6
    elif enriched.icp_fit_score >= 50:
        score += 0.3

    if enriched.data_completeness_score >= 90:
        score += 0.4
    elif enriched.data_completeness_score >= 70:
        score += 0.2

    if matches:
        top_score = matches[0].score
        if top_score >= 60:
            score += 0.5
        elif top_score >= 45:
            score += 0.2
        delta = (matches[0].score - matches[1].score) if len(matches) > 1 else 0
        if delta >= 15:
            score += 0.3

    company_lower = enriched.account.company.lower()
    body_lower = email.body.lower()
    if company_lower in body_lower:
        score += 0.3

    # --- negative signals ---
    first_line = email.body.splitlines()[0].lower() if email.body.splitlines() else ""
    if first_line.startswith("hi there"):
        score -= 0.8
        flags.append("LOW_PERSONALIZATION")

    if enriched.data_completeness_score < 60:
        score -= 0.5
        flags.append("SPARSE_INPUT_DATA")

    if "would you be open" not in body_lower and "schedule" not in body_lower:
        score -= 0.4
        flags.append("WEAK_CTA")

    if not enriched.account.contact.name:
        score -= 0.3
        flags.append("NO_CONTACT_IDENTIFIED")

    score = round(max(1.0, min(5.0, score)), 1)
    human_review = score < 3.0 or "LOW_PERSONALIZATION" in flags
    return score, human_review, flags
