from __future__ import annotations

from src.agents.prospecting.evaluator import evaluate_output
from src.agents.prospecting.generator import generate_outreach
from src.agents.verification.flagger import flag_actions
from src.schemas.account import EnrichedAccount
from src.schemas.audit import JudgeResult
from src.schemas.map_verification import ParsedEvidence, VerificationOutput
from src.schemas.prospecting import ProspectingOutput, ValuePropMatch


def apply_prospecting_corrections(
    enriched: EnrichedAccount,
    matches: list[ValuePropMatch],
    prior: ProspectingOutput,
    judge: JudgeResult,
) -> ProspectingOutput:
    """Regenerate outreach incorporating judge feedback; re-evaluate quality."""
    email, questions, _prov = generate_outreach(
        enriched,
        matches,
        correction_feedback=judge.correction_suggestions,
        prior_email=prior.email,
    )
    score, human_review, flags = evaluate_output(enriched, email)
    return ProspectingOutput(
        account_id=prior.account_id,
        matched_value_props=prior.matched_value_props,
        email=email,
        discovery_questions=questions,
        quality_score=score,
        human_review_needed=human_review,
        flags=list(dict.fromkeys(enriched.flags + flags)),
    )


def apply_map_correction(
    parsed: ParsedEvidence,
    prior: VerificationOutput,
    evidence_text: str,
) -> VerificationOutput:
    """Deterministic fixes when judge flags tier issues (bounded, no LLM)."""
    tier = prior.confidence_tier
    score = prior.confidence_score
    risks = list(prior.risk_factors)
    lower = evidence_text.lower()

    if parsed.source_directness != "first_party" and tier == "HIGH":
        tier = "MEDIUM"
        score = min(score, 74)
        risks.append("AUDIT_TIER_CAP")

    if ("exploring" in lower or "no commitment" in lower) and tier != "LOW":
        tier = "LOW"
        score = min(score, 40)
        risks.append("AUDIT_EXPLORATORY_CAP")

    if "slack" in lower and "ae" in lower and tier == "HIGH":
        tier = "MEDIUM"
        score = min(score, 70)
        risks.append("AUDIT_CHANNEL_DOWNGRADE")

    actions = flag_actions(tier, risks)
    return VerificationOutput(
        evidence_id=prior.evidence_id,
        confidence_score=score,
        confidence_tier=tier,
        risk_factors=sorted(set(risks)),
        recommended_actions=actions,
    )
