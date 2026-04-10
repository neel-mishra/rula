"""Comprehensive v3 Stage 4 test suite.

Covers:
- Value-prop scoring engine (taxonomy, signals, attribution, saturation)
- Segment logic (overrides, competitor mapping, wedge derivation)
- Context fetch (fallback order, flags)
- Prompt contracts (email + discovery questions)
- Policy validator (required claims, banned terms, paragraph count)
- Deterministic fallback compliance
- Explainability specificity scoring
"""
from __future__ import annotations

import json
from pathlib import Path


from src.agents.prospecting.context_fetch import CompanyContext, fetch_company_context
from src.agents.prospecting.enrichment import enrich_account
from src.agents.prospecting.generator import (
    BANNED_TERMS,
    _deterministic_email_v3,
    _deterministic_questions_v3,
    _validate_email,
    _validate_questions,
)
from src.agents.prospecting.matcher import match_value_props, match_value_props_detailed
from src.agents.prospecting.segment_logic import (
    SEGMENT_COMPETITORS,
    WEDGE_MAP,
    SegmentContext,
    resolve_segment_context,
)
from src.agents.prospecting.value_prop_scoring import (
    BASE_SCORE,
    SCORING_VERSION,
    score_value_props,
)
from src.agents.prospecting.value_prop_taxonomy import (
    extract_context_signals,
    normalize_health_plan,
    normalize_industry,
)
from src.explainability.value_prop_reasoner import (
    _build_template_explanation,
    _score_specificity,
)
from src.providers.prompts import (
    SYSTEM_GTM_STRATEGIST,
    discovery_questions_prompt_v3,
    email_prompt_v3,
)
from src.schemas.account import Account, Contact, EnrichedAccount
from src.schemas.prospecting import ValuePropMatch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_account(**overrides) -> Account:
    defaults = dict(
        account_id=1,
        company="Acme Health",
        industry="Health System",
        us_employees=12000,
        contact=Contact(name="Sarah Chen", title="VP Benefits"),
        health_plan="Anthem",
        notes="High turnover in nursing staff, exploring EAP options",
    )
    defaults.update(overrides)
    return Account(**defaults)


def _make_enriched(account: Account | None = None) -> EnrichedAccount:
    return enrich_account(account or _make_account())


def _all_accounts() -> list[Account]:
    raw = json.loads(Path("data/accounts.json").read_text(encoding="utf-8"))
    return [Account.model_validate(a) for a in raw]


# ===================================================================
# 1. Value-Prop Taxonomy
# ===================================================================

class TestIndustryNormalization:
    def test_health_system_aliases(self):
        for raw in ["Healthcare", "Health System", "Hospital Network", "Medical Center"]:
            assert normalize_industry(raw) == "health_system"

    def test_university_aliases(self):
        for raw in ["University", "Higher Education", "College", "Academic"]:
            assert normalize_industry(raw) == "university"

    def test_unknown_maps_to_other(self):
        assert normalize_industry("Quantum Physics Labs") == "other"


class TestHealthPlanNormalization:
    def test_anthem_variants(self):
        for raw in ["Anthem", "Elevance", "WellPoint"]:
            _, family = normalize_health_plan(raw)
            assert family == "anthem"

    def test_unknown_plan(self):
        canon, family = normalize_health_plan(None)
        assert canon == "unknown"
        assert family == "unknown"

    def test_unrecognized_plan(self):
        canon, family = normalize_health_plan("Local Mutual Benefit")
        assert family == "other"


class TestContextSignalExtraction:
    def test_finds_turnover_signal(self):
        hits = extract_context_signals("High turnover in nursing staff")
        buckets = [h["bucket"] for h in hits]
        assert "workforce_productivity" in buckets

    def test_finds_eap_signal(self):
        hits = extract_context_signals("Current EAP contract expires Q2")
        assert any(h["bucket"] == "eap_upgrade" for h in hits)

    def test_empty_text_returns_empty(self):
        assert extract_context_signals("") == []


# ===================================================================
# 2. Value-Prop Scoring Engine
# ===================================================================

class TestScoringEngine:
    def test_all_props_start_at_base(self):
        acct = _make_account(industry="Unknown", notes="", health_plan="Unknown")
        enriched = enrich_account(acct)
        result = score_value_props(enriched)
        for m in result.matches:
            assert m.score >= BASE_SCORE - 10

    def test_health_system_boosts_cost_of_care(self):
        enriched = _make_enriched(_make_account(industry="Health System"))
        result = score_value_props(enriched)
        tcoc = next(m for m in result.matches if m.value_prop == "total_cost_of_care")
        assert tcoc.score > BASE_SCORE

    def test_university_boosts_eap_and_access(self):
        enriched = _make_enriched(_make_account(industry="University"))
        result = score_value_props(enriched)
        eap = next(m for m in result.matches if m.value_prop == "eap_upgrade")
        access = next(m for m in result.matches if m.value_prop == "employee_access")
        assert eap.score > BASE_SCORE
        assert access.score > BASE_SCORE

    def test_attribution_present(self):
        enriched = _make_enriched()
        result = score_value_props(enriched)
        assert len(result.attributions) > 0
        for attr in result.attributions:
            assert attr.source_field in {"industry", "us_employees", "health_plan", "notes", "interaction"}

    def test_scoring_version_set(self):
        enriched = _make_enriched()
        result = score_value_props(enriched)
        assert result.scoring_version == SCORING_VERSION

    def test_scores_vary_across_accounts(self):
        accounts = _all_accounts()
        top_scores = set()
        for acct in accounts:
            enriched = enrich_account(acct)
            result = score_value_props(enriched)
            top_scores.add(result.matches[0].score)
        assert len(top_scores) > 1

    def test_top_props_vary_across_accounts(self):
        accounts = _all_accounts()
        top_props = set()
        for acct in accounts:
            enriched = enrich_account(acct)
            result = score_value_props(enriched)
            top_props.add(result.matches[0].value_prop)
        assert len(top_props) > 1

    def test_deterministic_tiebreak(self):
        acct = _make_account(industry="Unknown", notes="", health_plan="Unknown")
        enriched = enrich_account(acct)
        r1 = score_value_props(enriched)
        r2 = score_value_props(enriched)
        assert [m.value_prop for m in r1.matches] == [m.value_prop for m in r2.matches]

    def test_matcher_delegates_to_v3_engine(self):
        enriched = _make_enriched()
        matches = match_value_props(enriched)
        detailed = match_value_props_detailed(enriched)
        assert [m.value_prop for m in matches] == [m.value_prop for m in detailed.matches]


# ===================================================================
# 3. Segment Logic
# ===================================================================

class TestSegmentLogic:
    def test_health_system_emphasizes_tcoc(self):
        matches = [ValuePropMatch(value_prop="employee_access", score=80, reasoning="test")]
        seg = resolve_segment_context("Health System", matches)
        assert seg.emphasis_vp == "total_cost_of_care"

    def test_university_emphasizes_access(self):
        matches = [ValuePropMatch(value_prop="eap_upgrade", score=80, reasoning="test")]
        seg = resolve_segment_context("University", matches)
        assert seg.emphasis_vp == "employee_access"

    def test_other_uses_top_match(self):
        matches = [ValuePropMatch(value_prop="eap_upgrade", score=80, reasoning="test")]
        seg = resolve_segment_context("Retail", matches)
        assert seg.emphasis_vp == "eap_upgrade"

    def test_competitor_set_for_known_segments(self):
        for segment_key in SEGMENT_COMPETITORS:
            assert SEGMENT_COMPETITORS[segment_key]

    def test_wedge_derived_from_emphasis_vp(self):
        matches = [ValuePropMatch(value_prop="eap_upgrade", score=80, reasoning="test")]
        seg = resolve_segment_context("University", matches)
        assert seg.wedge == WEDGE_MAP["employee_access"]


# ===================================================================
# 4. Context Fetch
# ===================================================================

class TestContextFetch:
    def test_returns_missing_context_flag_for_placeholder(self):
        ctx = fetch_company_context("Jane Doe", "Acme Corp")
        assert ctx.source_type == "none"
        assert "MISSING_CONTEXT" in ctx.flags

    def test_never_raises(self):
        ctx = fetch_company_context("", "")
        assert isinstance(ctx, CompanyContext)


# ===================================================================
# 5. Prompt Contracts
# ===================================================================

class TestEmailPromptV3:
    def test_contains_banned_list(self):
        prompt = email_prompt_v3(
            prospect_name="Sarah",
            company_name="Acme",
            company_context="expansion news",
            segment_label="Health System",
            health_plan="Anthem",
            mapped_value_prop="total_cost_of_care",
            similar_competitor="similar health systems",
        )
        assert "Strict Banned List" in prompt
        assert "revolutionary" in prompt.lower()

    def test_contains_segment_logic(self):
        prompt = email_prompt_v3(
            prospect_name="Sarah",
            company_name="Acme",
            company_context="news",
            segment_label="University",
            health_plan="Aetna",
            mapped_value_prop="employee_access",
            similar_competitor="peer universities",
        )
        assert "University" in prompt
        assert "Student/Staff Access" in prompt

    def test_contains_campaign_playbook_cta(self):
        prompt = email_prompt_v3(
            prospect_name="Sarah",
            company_name="Acme",
            company_context="news",
            segment_label="Health System",
            health_plan="Anthem",
            mapped_value_prop="total_cost_of_care",
            similar_competitor="similar health systems",
        )
        assert "campaign playbook" in prompt.lower()


class TestDiscoveryQuestionsPromptV3:
    def test_contains_strategic_wedge_categories(self):
        prompt = discovery_questions_prompt_v3(
            prospect_name="Sarah",
            company_context="wellness expansion",
            health_plan="Anthem",
            mapped_value_prop="total_cost_of_care",
            wedge="rising health costs",
        )
        assert "Engagement Gap" in prompt
        assert "Friction Point" in prompt
        assert "Future Commitment" in prompt

    def test_system_role_is_gtm_strategist(self):
        assert "elite GTM Strategist" in SYSTEM_GTM_STRATEGIST


# ===================================================================
# 6. Policy Validators
# ===================================================================

class TestEmailValidator:
    def _seg(self, segment: str = "health_system") -> SegmentContext:
        return SegmentContext(
            segment=segment,
            emphasis_vp="total_cost_of_care",
            segment_label="Health System",
            similar_competitor="similar health systems",
            wedge="rising health costs",
        )

    def test_passes_compliant_email(self):
        from src.schemas.prospecting import OutreachEmail
        email = OutreachEmail(
            subject_line="Acme wellness engagement",
            body=(
                "Noticed your recent expansion. Maintaining a high-performing workforce is challenging.\n\n"
                "Rula is free for the employer and works with Anthem to reduce total cost of care.\n\n"
                "We handle the provider network and the internal marketing campaigns."
            ),
            cta="Open to seeing the campaign playbook?",
        )
        violations = _validate_email(email, self._seg())
        assert violations == []

    def test_catches_missing_free_claim(self):
        from src.schemas.prospecting import OutreachEmail
        email = OutreachEmail(
            subject_line="Test",
            body="Para 1.\n\nPara 2.\n\nPara 3.",
            cta="test",
        )
        violations = _validate_email(email, self._seg())
        assert any("free" in v.lower() for v in violations)

    def test_catches_banned_terms(self):
        from src.schemas.prospecting import OutreachEmail
        email = OutreachEmail(
            subject_line="Test",
            body="We are excited to reach out about this revolutionary platform.\n\nFree for the employer and cost of care.\n\nPara 3.",
            cta="test",
        )
        violations = _validate_email(email, self._seg())
        banned_found = [v for v in violations if "Banned term" in v]
        assert len(banned_found) >= 2


class TestQuestionsValidator:
    def test_passes_valid_questions(self):
        qs = [
            "How do you measure engagement?",
            "What feedback have you received?",
            "What does your comms process look like?",
        ]
        assert _validate_questions(qs) == []

    def test_catches_wrong_count(self):
        violations = _validate_questions(["Q1?", "Q2?"])
        assert any("Expected at least" in v for v in violations)


# ===================================================================
# 7. Deterministic Fallbacks
# ===================================================================

class TestDeterministicFallbacks:
    def test_email_v3_is_policy_compliant(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        email = _deterministic_email_v3(enriched, seg, "")
        violations = _validate_email(email, seg)
        assert violations == [], f"Deterministic email has violations: {violations}"

    def test_email_v3_mentions_company(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        email = _deterministic_email_v3(enriched, seg, "")
        assert "Acme Health" in email.body or "Acme Health" in email.subject_line

    def test_email_v3_uses_context_when_available(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        email = _deterministic_email_v3(
            enriched,
            seg,
            "launched new wellness initiative",
            context_source_type="news",
        )
        assert "wellness initiative" in email.body.lower()

    def test_questions_v3_returns_three(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "")
        assert len(qs) == 3
        for q in qs:
            assert q.endswith("?")

    def test_questions_v3_does_not_claim_recent_when_context_missing(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "", context_source_type="none")
        assert "recent" not in qs[0].lower()

    def test_questions_v3_uses_recent_only_for_web_context(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(
            enriched,
            seg,
            "launched a new workforce wellness initiative",
            context_source_type="news",
        )
        assert "recent update" in qs[0].lower()

    def test_questions_v3_prefers_size_wording_when_context_missing(self):
        enriched = _make_enriched(_make_account(notes="Post-merger consolidation; HR team stretched thin"))
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "", context_source_type="none")
        assert "size of your workforce" in qs[0].lower()
        assert "note about" not in qs[0].lower()

    def test_questions_v3_normalizes_staff_student_notes_phrase(self):
        enriched = _make_enriched(
            _make_account(
                us_employees=14000,
                notes="Includes 6,000 staff + 8,000 student employees; wellness program refresh underway",
            )
        )
        seg = resolve_segment_context("University", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "", context_source_type="none")
        q1 = qs[0].lower()
        assert "combined ~14,000 staff and students" in q1
        assert "includes 6,000 staff + 8,000 student employees" not in q1

    def test_questions_v3_uses_benefits_setup_when_size_missing(self):
        acct = _make_account(us_employees=0, health_plan="Aetna", notes="")
        enriched = _make_enriched(acct)
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "", context_source_type="none")
        assert "benefits setup with aetna" in qs[0].lower()

    def test_questions_v3_uses_footprint_when_size_and_plan_missing(self):
        acct = _make_account(
            us_employees=0,
            health_plan="",
            notes="Given 3 hospitals and 12 outpatient clinics across the Midwest",
        )
        enriched = _make_enriched(acct)
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "", context_source_type="none")
        q1 = qs[0].lower()
        assert "your footprint" in q1
        assert "3 hospitals and 12 outpatient clinics across the midwest" in q1

    def test_questions_v3_references_health_plan(self):
        enriched = _make_enriched()
        seg = resolve_segment_context("Health System", match_value_props(enriched))
        qs = _deterministic_questions_v3(enriched, seg, "")
        combined = " ".join(qs).lower()
        assert "anthem" in combined

    def test_no_banned_terms_in_deterministic_email(self):
        for acct in _all_accounts():
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            seg = resolve_segment_context(acct.industry, matches)
            email = _deterministic_email_v3(enriched, seg, "")
            body_lower = email.body.lower()
            for term in BANNED_TERMS:
                assert term not in body_lower, (
                    f"Banned term '{term}' found in email for {acct.company}"
                )


# ===================================================================
# 8. Explainability Specificity
# ===================================================================

class TestSpecificityScoring:
    def test_template_explanation_meets_threshold(self):
        enriched = _make_enriched()
        result = score_value_props(enriched)
        top_match = result.matches[0]
        explanation = _build_template_explanation(
            top_match, enriched, result.attributions, result.matches
        )
        spec = _score_specificity(explanation, enriched.account.company, result.attributions)
        assert spec >= 50, f"Template explanation specificity too low: {spec}"

    def test_company_name_in_template_explanation(self):
        enriched = _make_enriched()
        result = score_value_props(enriched)
        explanation = _build_template_explanation(
            result.matches[0], enriched, result.attributions, result.matches
        )
        assert "Acme Health" in explanation

    def test_runner_up_comparison_in_template(self):
        enriched = _make_enriched()
        result = score_value_props(enriched)
        explanation = _build_template_explanation(
            result.matches[0], enriched, result.attributions, result.matches
        )
        assert "outranked" in explanation.lower()


# ===================================================================
# 9. End-to-end integration (no LLM)
# ===================================================================

class TestEndToEndDeterministic:
    """Run the full pipeline for all test accounts using deterministic fallbacks."""

    def test_all_accounts_produce_valid_output(self):
        for acct in _all_accounts():
            enriched = enrich_account(acct)
            matches = match_value_props(enriched)
            seg = resolve_segment_context(acct.industry, matches)
            email = _deterministic_email_v3(enriched, seg, "")
            qs = _deterministic_questions_v3(enriched, seg, "")
            violations = _validate_email(email, seg)
            assert violations == [], f"{acct.company}: {violations}"
            assert len(qs) == 3
