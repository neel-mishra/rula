from __future__ import annotations

from src.config import load_config
from src.schemas.account import Account, EnrichedAccount
from src.schemas.audit import JudgeResult
from src.schemas.map_verification import ParsedEvidence, VerificationOutput
from src.schemas.prospecting import ProspectingOutput


def judge_prospecting(
    output: ProspectingOutput,
    account: Account,
    enriched: EnrichedAccount,
) -> JudgeResult:
    """Independent rubric check on prospecting output (heuristic stand-in for GPT-4o judge)."""
    suggestions: list[str] = []
    score = 5.0

    company = account.company
    in_subject = company.lower() in output.email.subject_line.lower()
    in_body = company.lower() in output.email.body.lower()
    if not in_subject and not in_body:
        score -= 1.5
        suggestions.append("Mention the account company name explicitly in subject or body.")

    if not account.contact.name and "there" in output.email.body[:80].lower():
        score -= 0.5
        suggestions.append("Sparse contact: keep professional tone without inventing a name.")

    min_q = load_config().min_discovery_questions
    if len(output.discovery_questions) < min_q:
        score -= 1.0
        suggestions.append(f"Provide at least {min_q} discovery questions.")

    if output.quality_score < 3.0:
        score -= 1.0
        suggestions.append("Improve personalization and CTA strength per quality evaluator.")

    top_vp = output.matched_value_props[0].value_prop if output.matched_value_props else ""
    ind = account.industry.lower()
    if "health" in ind and top_vp not in {"total_cost_of_care", "workforce_productivity", "eap_upgrade"}:
        score -= 0.5
        suggestions.append("Re-check value prop alignment for health system segment.")

    score = max(0.0, min(5.0, score))
    pass_audit = score >= 3.0
    if not in_subject and not in_body:
        pass_audit = False

    return JudgeResult(
        pass_audit=pass_audit,
        audit_score=score,
        reasoning="Heuristic judge: company reference, question count, quality alignment.",
        correction_suggestions=suggestions,
    )


def judge_map_verification(
    output: VerificationOutput,
    evidence_text: str,
    parsed: ParsedEvidence,
) -> JudgeResult:
    """Check confidence tier proportionality vs evidence (heuristic stand-in)."""
    suggestions: list[str] = []
    score = 5.0
    lower = evidence_text.lower()

    if parsed.source_directness != "first_party" and output.confidence_tier == "HIGH":
        score = 1.0
        suggestions.append("Secondhand evidence cannot be HIGH; downgrade to MEDIUM or lower.")

    if ("exploring" in lower or "no commitment" in lower) and output.confidence_tier != "LOW":
        score = min(score, 2.0)
        suggestions.append("Exploratory language should map to LOW tier.")

    if parsed.source_directness == "first_party" and "excited" in lower and output.confidence_tier == "LOW":
        score -= 1.0
        suggestions.append("Strong first-party commitment may warrant higher tier; re-check scoring.")

    if "slack" in lower and "ae" in lower and output.confidence_tier == "HIGH":
        score = min(score, 2.5)
        suggestions.append("AE-reported Slack should not be HIGH without corroboration.")

    score = max(0.0, min(5.0, score))
    pass_audit = score >= 3.0 and output.confidence_tier in {"HIGH", "MEDIUM", "LOW"}
    if parsed.source_directness != "first_party" and output.confidence_tier == "HIGH":
        pass_audit = False

    return JudgeResult(
        pass_audit=pass_audit,
        audit_score=score,
        reasoning="Heuristic judge: source directness vs tier, language firmness, channel risk.",
        correction_suggestions=suggestions,
    )
