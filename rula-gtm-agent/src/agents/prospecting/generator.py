from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from src.agents.prospecting.context_fetch import fetch_company_context
from src.agents.prospecting.segment_logic import SegmentContext, resolve_segment_context
from src.config import load_config
from src.providers.base import GenerationRequest
from src.providers.prompts import (
    SYSTEM_GTM_STRATEGIST,
    SYSTEM_SALES,
    discovery_questions_prompt_v3,
    email_prompt_v3,
)
from src.providers.router import ModelRouter
from src.schemas.account import EnrichedAccount
from src.schemas.prospecting import OutreachEmail, ValuePropMatch

logger = logging.getLogger(__name__)

BANNED_TERMS = [
    "revolutionary", "pioneering", "help", "excited",
    "reached out", "checking in",
]


def _get_banned_terms() -> list[str]:
    """Merge hardcoded banned terms with business DNA voice constraints."""
    terms = list(BANNED_TERMS)
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            for t in reg.bundle.voice.banned_terms:
                if t.lower() not in terms:
                    terms.append(t.lower())
    except Exception:
        pass
    return terms

# ---------------------------------------------------------------------------
# Generation provenance (carried through to output)
# ---------------------------------------------------------------------------

@dataclass
class GenerationProvenance:
    context_source: str = "none"
    context_snippet: str = ""
    context_url: str = ""
    segment_label: str = ""
    emphasis_vp: str = ""
    competitor_token: str = ""
    wedge: str = ""
    email_provider: str = ""
    email_prompt_version: str = "v3"
    email_validation_passed: bool = True
    email_repair_attempted: bool = False
    email_fallback_used: bool = False
    questions_provider: str = ""
    questions_prompt_version: str = "v3"
    questions_validation_passed: bool = True
    questions_repair_attempted: bool = False
    questions_fallback_used: bool = False
    business_dna_version: str = ""
    business_dna_hash: str = ""
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Policy validators
# ---------------------------------------------------------------------------

def _validate_email(email: OutreachEmail, seg: SegmentContext) -> list[str]:
    """Return list of violation descriptions. Empty = valid."""
    violations: list[str] = []
    body = email.body
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(paragraphs) < 3:
        violations.append(f"Expected 3 paragraphs, found {len(paragraphs)}")

    lower_body = body.lower()
    if "free for the employer" not in lower_body and "free for" not in lower_body:
        violations.append("Missing required claim: Rula is free for the employer")
    if seg.segment == "health_system" and "cost of care" not in lower_body:
        violations.append("Health System segment must focus on Total Cost of Care")
    if seg.segment == "university" and "access" not in lower_body:
        violations.append("University segment must focus on Student/Staff Access")

    first_sentence = body.split(".")[0].lower() if "." in body else lower_body[:200]
    if "partnership" in first_sentence:
        violations.append("'partnership' banned in first sentence")

    for term in _get_banned_terms():
        if term in lower_body:
            violations.append(f"Banned term found: '{term}'")

    return violations


def _validate_questions(questions: list[str]) -> list[str]:
    """Validate discovery questions against Strategic Wedge categories."""
    violations: list[str] = []
    need = load_config().min_discovery_questions
    if len(questions) < need:
        violations.append(f"Expected at least {need} questions, got {len(questions)}")
    for q in questions:
        if not q.strip().endswith("?"):
            violations.append(f"Question does not end with '?': {q[:50]}")
    return violations


# ---------------------------------------------------------------------------
# Deterministic fallback templates (v3 compliant)
# ---------------------------------------------------------------------------

def _clean_excerpt(text: str, *, max_len: int = 120) -> str:
    """Normalize free-text snippets into a safe, readable excerpt."""
    t = " ".join((text or "").strip().split())
    if len(t) <= max_len:
        return t
    return t[:max_len].rstrip() + "…"


def _extract_int(text: str) -> int | None:
    cleaned = text.replace(",", "").strip()
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def _extract_notes_footprint_phrase(notes: str) -> str | None:
    """Extract a normalized footprint noun phrase from notes via strict patterns."""
    if not notes:
        return None
    lower = notes.lower()

    hosp_match = re.search(r"(\d[\d,]*)\s+hospitals?\b", lower)
    clinic_match = re.search(
        r"(\d[\d,]*)\s+(?:outpatient\s+)?clinics?\b",
        lower,
    )
    region_match = re.search(
        r"\b(across|in)\s+the\s+(midwest|northeast|southeast|southwest|west|east)\b",
        lower,
    )

    hosp = _extract_int(hosp_match.group(1)) if hosp_match else None
    clinic = _extract_int(clinic_match.group(1)) if clinic_match else None
    region = region_match.group(2).title() if region_match else None

    if hosp is None and clinic is None:
        return None

    parts: list[str] = []
    if hosp is not None:
        parts.append(f"{hosp:,} hospital" + ("s" if hosp != 1 else ""))
    if clinic is not None:
        parts.append(f"{clinic:,} outpatient clinic" + ("s" if clinic != 1 else ""))

    if len(parts) == 2:
        phrase = f"{parts[0]} and {parts[1]}"
    else:
        phrase = parts[0]

    if region:
        return f"your footprint ({phrase} across the {region})"
    return f"your footprint ({phrase})"


def _extract_notes_staff_student_phrase(notes: str) -> str | None:
    """Extract normalized 'combined staff and students' phrase via strict patterns."""
    if not notes:
        return None
    lower = notes.lower()

    staff_match = re.search(r"(\d[\d,]*)\s+staff\b", lower)
    student_match = re.search(r"(\d[\d,]*)\s+student(?:s|\s+employees?)?\b", lower)
    if not staff_match or not student_match:
        return None

    staff = _extract_int(staff_match.group(1))
    students = _extract_int(student_match.group(1))
    if staff is None or students is None:
        return None

    combined = staff + students
    return f"a combined ~{combined:,} staff and students"


def _deterministic_email_v3(
    enriched: EnrichedAccount,
    seg: SegmentContext,
    company_context: str,
    *,
    context_source_type: str = "none",
) -> OutreachEmail:
    """Policy-compliant deterministic email when LLM fails."""
    company = enriched.account.company
    contact = enriched.account.contact.name or "there"
    hp = enriched.account.health_plan or "your current carrier"

    # Only treat context as "recent" when it is actually sourced from a recency-bearing
    # retrieval mechanism (e.g., LinkedIn/news). Never imply recency for notes, size, etc.
    has_recent_context = context_source_type in {"linkedin", "news"} and bool(company_context.strip())
    if has_recent_context:
        p1 = (
            f"{contact},\n\n"
            f"Noticed {company}'s recent update: {company_context[:120]}. "
            "Sustaining a high-performing workforce through that kind of change "
            "takes more than a benefits line item."
        )
    else:
        p1 = (
            f"{contact},\n\n"
            f"Running a team of {enriched.account.us_employees:,} at {company} "
            "means workforce performance depends on more than just having a benefits package."
        )

    if seg.segment == "health_system":
        p2 = (
            f"Rula partners with health systems to reduce total cost of care. "
            f"The platform is free for the employer and works with {hp} "
            "to remove financial friction for employees seeking behavioral health support."
        )
    elif seg.segment == "university":
        p2 = (
            f"Rula partners with universities to close the student and staff access gap. "
            f"The platform is free for the employer and works with {hp} "
            "to remove financial friction for those seeking behavioral health support."
        )
    else:
        p2 = (
            f"Rula is free for the employer and works with {hp} "
            "to remove financial friction. We handle the provider network and "
            "the internal marketing campaigns so your team doesn't have to."
        )

    p3 = (
        "We handle the provider network and the internal marketing campaigns "
        "so your team doesn't have to."
    )

    body = f"{p1}\n\n{p2}\n\n{p3}"
    cta = f"Open to seeing the campaign playbook we used to drive utilization at {seg.similar_competitor}?"
    subject = f"{company} wellness engagement"

    return OutreachEmail(subject_line=subject, body=body, cta=cta)


def _deterministic_questions_v3(
    enriched: EnrichedAccount,
    seg: SegmentContext,
    company_context: str,
    *,
    context_source_type: str = "none",
) -> list[str]:
    """Policy-compliant deterministic discovery questions when LLM fails."""
    hp = enriched.account.health_plan or "your current plan"

    def _safe_ctx_ref() -> str:
        raw = (company_context or "").strip()
        # Only use "recent" phrasing when we truly have web/news context.
        if context_source_type in {"linkedin", "news"} and raw:
            return f"your recent update: {raw[:60]}"

        notes = (enriched.account.notes or "").strip()
        industry = enriched.account.industry or "your industry"
        size = enriched.account.us_employees

        # Priority 1: workforce size (plus strict notes normalization for staff+students)
        if isinstance(size, int) and size > 0:
            combined_phrase = _extract_notes_staff_student_phrase(notes)
            if combined_phrase:
                return combined_phrase
            return f"the size of your workforce (~{size:,} people)"

        # Priority 2: benefits setup
        if hp and hp != "your current plan":
            return f"your benefits setup with {hp}"

        # Priority 3: strict footprint inference from notes
        footprint_phrase = _extract_notes_footprint_phrase(notes)
        if footprint_phrase:
            return footprint_phrase

        # Priority 4: operating environment
        return f"your operating environment as a {industry} employer"

    ctx_ref = _safe_ctx_ref()

    return [
        f"Given {ctx_ref}, how are you measuring whether employees are actually using the behavioral health benefits available to them?",
        f"With {hp} as your carrier, what feedback have you received from employees about finding in-network mental health providers?",
        "What does your internal employee communications process look like today for promoting available benefits?",
    ]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _try_parse_email(raw: str) -> OutreachEmail | None:
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        if isinstance(data, dict) and "subject_line" in data and "body" in data:
            return OutreachEmail(
                subject_line=data["subject_line"],
                body=data["body"],
                cta=data.get("cta", ""),
            )
    except Exception:
        pass
    return None


def _try_parse_questions(raw: str) -> list[str] | None:
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        if isinstance(data, list) and all(isinstance(q, str) for q in data) and len(data) >= 2:
            return data
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main generation pipeline (v3)
# ---------------------------------------------------------------------------

def generate_outreach(
    enriched: EnrichedAccount,
    matches: list[ValuePropMatch],
    correction_feedback: list[str] | None = None,
    prior_email: OutreachEmail | None = None,
) -> tuple[OutreachEmail, list[str]]:
    """v3 generation pipeline with strict prompts, validation, and repair."""
    cfg = load_config()
    router = ModelRouter(cfg)
    prov = GenerationProvenance()

    if cfg.business_dna_enabled:
        try:
            from src.context.business_context import BusinessContextRegistry
            reg = BusinessContextRegistry.get()
            prov.business_dna_version = reg.bundle.version
            prov.business_dna_hash = reg.bundle.content_hash
        except Exception:
            prov.flags.append("BUSINESS_DNA_LOAD_FAILED")

    prospect_name = enriched.account.contact.name or "there"
    company = enriched.account.company
    hp = enriched.account.health_plan or "your current carrier"

    seg = resolve_segment_context(enriched.account.industry, matches)
    prov.segment_label = seg.segment_label
    prov.emphasis_vp = seg.emphasis_vp
    prov.competitor_token = seg.similar_competitor
    prov.wedge = seg.wedge

    ctx = fetch_company_context(prospect_name, company)
    prov.context_source = ctx.source_type
    prov.context_snippet = ctx.context_snippet
    prov.context_url = ctx.source_url
    prov.flags.extend(ctx.flags)

    # company_context: only actual recent context snippet (if available).
    company_context = ctx.context_snippet.strip() if (ctx.context_snippet and ctx.context_snippet.strip()) else ""

    # prompt_company_context: always provide a coherent context string to the prompt,
    # even when web context is missing (notes -> size/industry -> generic).
    notes = (enriched.account.notes or "").strip()
    if company_context:
        prompt_company_context = company_context
    elif notes:
        prompt_company_context = _clean_excerpt(notes, max_len=120)
    else:
        industry = enriched.account.industry or "your industry"
        size = enriched.account.us_employees
        size_ref = f"~{size:,}" if isinstance(size, int) and size > 0 else "your"
        wedge = (seg.wedge or "").strip()
        wedge_tail = f"; wedge: {_clean_excerpt(wedge, max_len=60)}" if wedge else ""
        prompt_company_context = f"workforce context: {size_ref} people in {industry}{wedge_tail}"

    # --- Email generation ---
    email: OutreachEmail | None = None
    email_req = GenerationRequest(
        content_type="email_v3",
        system=SYSTEM_SALES,
        prompt=email_prompt_v3(
            prospect_name=prospect_name,
            company_name=company,
            company_context=prompt_company_context,
            segment_label=seg.segment_label,
            health_plan=hp,
            mapped_value_prop=seg.emphasis_vp,
            similar_competitor=seg.similar_competitor,
        ),
        temperature=0.4,
    )
    email_resp = router.generate(email_req)
    if email_resp.ok:
        email = _try_parse_email(email_resp.text)
        prov.email_provider = email_resp.provider

    if email is not None:
        violations = _validate_email(email, seg)
        if violations:
            prov.email_validation_passed = False
            prov.email_repair_attempted = True
            logger.warning("Email validation failed: %s; attempting repair", violations)
            repair_prompt = email_req.prompt + (
                "\n\nThe previous output had these policy violations. "
                "Fix them and return corrected JSON:\n"
                + "\n".join(f"- {v}" for v in violations)
            )
            repair_req = GenerationRequest(
                content_type="email_v3",
                system=SYSTEM_SALES,
                prompt=repair_prompt,
                temperature=0.2,
            )
            repair_resp = router.generate(repair_req)
            repaired = _try_parse_email(repair_resp.text) if repair_resp.ok else None
            if repaired and not _validate_email(repaired, seg):
                email = repaired
                prov.email_validation_passed = True
            else:
                email = None

    if email is None:
        prov.email_fallback_used = True
        prov.flags.append("TEMPLATE_FALLBACK_USED")
        email = _deterministic_email_v3(
            enriched,
            seg,
            company_context,
            context_source_type=ctx.source_type,
        )

    # --- Discovery questions generation ---
    questions: list[str] | None = None
    q_req = GenerationRequest(
        content_type="discovery_questions_v3",
        system=SYSTEM_GTM_STRATEGIST,
        prompt=discovery_questions_prompt_v3(
            prospect_name=prospect_name,
            company_context=prompt_company_context,
            health_plan=hp,
            mapped_value_prop=seg.emphasis_vp,
            wedge=seg.wedge,
        ),
        temperature=0.3,
    )
    q_resp = router.generate(q_req)
    if q_resp.ok:
        questions = _try_parse_questions(q_resp.text)
        prov.questions_provider = q_resp.provider

    if questions is not None:
        q_violations = _validate_questions(questions)
        if q_violations:
            prov.questions_validation_passed = False
            prov.questions_repair_attempted = True
            logger.warning("Questions validation failed: %s; attempting repair", q_violations)
            q_repair_prompt = q_req.prompt + (
                "\n\nThe previous output had these issues. Fix and return corrected JSON array:\n"
                + "\n".join(f"- {v}" for v in q_violations)
            )
            q_repair_req = GenerationRequest(
                content_type="discovery_questions_v3",
                system=SYSTEM_GTM_STRATEGIST,
                prompt=q_repair_prompt,
                temperature=0.2,
            )
            q_repair_resp = router.generate(q_repair_req)
            repaired_q = _try_parse_questions(q_repair_resp.text) if q_repair_resp.ok else None
            if repaired_q and not _validate_questions(repaired_q):
                questions = repaired_q
                prov.questions_validation_passed = True
            else:
                questions = None

    if questions is None:
        prov.questions_fallback_used = True
        if "TEMPLATE_FALLBACK_USED" not in prov.flags:
            prov.flags.append("TEMPLATE_FALLBACK_USED")
        questions = _deterministic_questions_v3(
            enriched,
            seg,
            company_context,
            context_source_type=ctx.source_type,
        )

    return email, questions, prov


def get_generation_provenance(
    enriched: EnrichedAccount,
    matches: list[ValuePropMatch],
) -> GenerationProvenance:
    """Build provenance metadata without running generation (for telemetry)."""
    seg = resolve_segment_context(enriched.account.industry, matches)
    ctx = fetch_company_context(
        enriched.account.contact.name or "",
        enriched.account.company,
    )
    prov = GenerationProvenance(
        context_source=ctx.source_type,
        context_snippet=ctx.context_snippet,
        segment_label=seg.segment_label,
        emphasis_vp=seg.emphasis_vp,
        competitor_token=seg.similar_competitor,
        wedge=seg.wedge,
    )
    prov.flags.extend(ctx.flags)
    return prov
