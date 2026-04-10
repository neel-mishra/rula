"""Gemini-backed value-prop explainability with account-specific evidence.

Replaces generic boilerplate explanations with evidence-grounded reasoning.
Falls back to deterministic template if Gemini is unavailable or output
fails specificity validation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.agents.prospecting.value_prop_scoring import SignalAttribution
from src.config import load_config
from src.providers.base import GenerationRequest
from src.providers.router import ModelRouter
from src.schemas.account import EnrichedAccount
from src.schemas.prospecting import ValuePropMatch

logger = logging.getLogger(__name__)


@dataclass
class ExplainabilityResult:
    explanation: str
    provider: str = "template"
    prompt_version: str = "v3"
    evidence_refs: list[str] = field(default_factory=list)
    specificity_score: int = 0
    fallback_used: bool = False
    context_version: str = ""
    context_hash: str = ""


def _score_specificity(
    explanation: str,
    company: str,
    attributions: list[SignalAttribution],
) -> int:
    """Compute specificity score (0-100) for an explanation."""
    score = 0
    lower = explanation.lower()

    distinct_signals = set()
    for attr in attributions:
        if attr.signal.lower() in lower or attr.matched_text.lower() in lower:
            distinct_signals.add(attr.signal)
    if len(distinct_signals) >= 2:
        score += 25

    ranked_phrases = ["outranked", "scored higher", "stronger", "beat", "over", "versus", "compared to"]
    if any(p in lower for p in ranked_phrases):
        score += 25

    if company.lower() in lower:
        source_bound = ["industry", "size", "health plan", "notes", "employees", "carrier"]
        if any(s in lower for s in source_bound):
            score += 25

    words = explanation.split()
    if len(set(words)) / max(len(words), 1) > 0.5:
        score += 25

    return score


def _build_template_explanation(
    match: ValuePropMatch,
    enriched: EnrichedAccount,
    attributions: list[SignalAttribution],
    all_matches: list[ValuePropMatch],
) -> str:
    """Deterministic template explanation from Stage 2 evidence."""
    vp_attrs = [a for a in attributions if a.value_prop in (match.value_prop, "_all") and a.weight > 0]
    signal_strs = [f"{a.matched_text} ({a.source_field}, +{a.weight})" for a in vp_attrs[:4]]
    company = enriched.account.company

    runner_up = None
    for m in all_matches:
        if m.value_prop != match.value_prop:
            runner_up = m
            break

    rank_line = ""
    if runner_up:
        delta = match.score - runner_up.score
        rank_line = (
            f" This prop outranked {runner_up.value_prop.replace('_', ' ')} "
            f"by {delta} points, driven by stronger signal alignment."
        )

    return (
        f"For {company}, {match.value_prop.replace('_', ' ')} scored {match.score}/100 "
        f"based on account-specific evidence.\n\n"
        f"Signals used: {', '.join(signal_strs) if signal_strs else 'baseline profile'}."
        f"{rank_line}"
    )


def explain_value_prop_v3(
    match: ValuePropMatch,
    enriched: EnrichedAccount,
    attributions: list[SignalAttribution],
    all_matches: list[ValuePropMatch],
) -> ExplainabilityResult:
    """Generate account-specific value-prop explanation.

    Uses Gemini (via ModelRouter) for rich reasoning with deterministic
    evidence constraints. Falls back to template if generation or
    specificity validation fails.
    """
    company = enriched.account.company
    vp_attrs = [a for a in attributions if a.value_prop in (match.value_prop, "_all") and a.weight > 0]
    evidence_refs = [f"{a.signal}: {a.matched_text} ({a.source_field})" for a in vp_attrs]

    ctx_version = ""
    ctx_hash = ""
    pillar_context = ""
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            ctx_version = reg.bundle.version
            ctx_hash = reg.bundle.content_hash
            block = reg.prompt_block(["pillars", "product"])
            if block:
                pillar_context = f"\n\nBusiness context:\n{block}\n"
    except Exception:
        pass

    runner_up = None
    for m in all_matches:
        if m.value_prop != match.value_prop:
            runner_up = m
            break

    rank_context = ""
    if runner_up:
        rank_context = (
            f"This prop scored {match.score}, versus the next-best "
            f"'{runner_up.value_prop.replace('_', ' ')}' at {runner_up.score}."
        )

    prompt = (
        f"Explain why '{match.value_prop.replace('_', ' ')}' is the right value proposition "
        f"for {company} ({enriched.account.industry}, {enriched.account.us_employees:,} employees, "
        f"health plan: {enriched.account.health_plan or 'unknown'}).\n\n"
        f"Evidence from scoring:\n" + "\n".join(f"- {ref}" for ref in evidence_refs) + "\n\n"
        f"{rank_context}\n\n"
        "Write exactly:\n"
        "1. One short paragraph explaining why this prop is relevant to THIS account.\n"
        "2. A 'Signals used:' line listing the concrete evidence.\n"
        "3. A 'Why this beat alternatives:' line referencing score deltas.\n\n"
        f"You MUST mention '{company}' by name and at least 2 specific signals. "
        "Do NOT use generic language."
        f"{pillar_context}"
    )

    cfg = load_config()
    router = ModelRouter(cfg)
    resp = router.generate(GenerationRequest(
        content_type="value_prop_explanation",
        system="You are a concise GTM analyst. Ground every statement in account-specific evidence.",
        prompt=prompt,
        temperature=0.2,
    ))

    if resp.ok and resp.text.strip():
        explanation = resp.text.strip()
        spec_score = _score_specificity(explanation, company, vp_attrs)
        if spec_score >= 75:
            return ExplainabilityResult(
                explanation=explanation,
                provider=resp.provider,
                evidence_refs=evidence_refs,
                specificity_score=spec_score,
                context_version=ctx_version,
                context_hash=ctx_hash,
            )
        logger.warning(
            "Explanation specificity too low (%d); falling back to template", spec_score
        )

    template = _build_template_explanation(match, enriched, attributions, all_matches)
    spec_score = _score_specificity(template, company, vp_attrs)
    return ExplainabilityResult(
        explanation=template,
        provider="template",
        evidence_refs=evidence_refs,
        specificity_score=spec_score,
        fallback_used=True,
        context_version=ctx_version,
        context_hash=ctx_hash,
    )
