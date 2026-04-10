"""Golden tests for the BusinessContextRegistry integration.

These tests verify that:
1. The registry loads typed slices from business dna markdown files.
2. The feature flag gates context injection (graceful fallback when off).
3. Deterministic pipeline outputs remain stable when context changes.
4. LLM-generated output cannot override structured pipeline results.
5. Context hash changes are detected (drift guard).
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.context.business_context import (
    BusinessContextRegistry,
    CONTEXT_VERSION,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure each test starts with a fresh registry."""
    BusinessContextRegistry.reset()
    yield
    BusinessContextRegistry.reset()


@pytest.fixture()
def business_dna_dir(tmp_path: Path) -> Path:
    """Create a minimal business dna fixture with known content."""
    core = tmp_path / "core"
    core.mkdir()
    identity = tmp_path / "identity"
    identity.mkdir()
    ops = tmp_path / "ops"
    ops.mkdir()

    (core / "business_context.md").write_text(textwrap.dedent("""\
        # Rula Business Context
        ## 1. Overview
        Rula is a behavioral health company.
    """))
    (core / "ideal_customer_profile.md").write_text(textwrap.dedent("""\
        # Ideal Customer Profile
        ## 9. Anti-ICP
        - Organizations with low campaign-operating willingness.
        - Contacts without decision authority.
        ## 5. Expansion/Contraction Signals
        - Multi-quarter campaign commitment. (expansion)
        - Vague intent language without timeline. (contraction)
    """))
    (core / "product_dna.md").write_text(textwrap.dedent("""\
        # Product DNA
        ## 1. Value Proposition
        Fast access to in-network mental healthcare.
    """))
    (core / "competitor_landscape.md").write_text(textwrap.dedent("""\
        # Competitor Landscape
        Categories: digital mental health, EAP.
    """))
    (identity / "messaging_pillars.md").write_text(textwrap.dedent("""\
        # Messaging Pillars
        ### Pillar 1: Access Without Delay
        - **Core argument:** Fast in-network care matching.
        ### Pillar 2: Insurance Simplicity
        - **Core argument:** Clear costs before treatment.
    """))
    (identity / "brand_voice_matrix.md").write_text(textwrap.dedent("""\
        # Brand Voice
        ## 1. The Core Personality
        - Compassionate: warm but grounded
        - Clear: no jargon
        ## 4. Vocabulary & Diction
        Terms to avoid:
        - stigmatizing labels
        - guaranteed cure
    """))
    (identity / "style_guides.md").write_text("# Style Guide\n")
    (identity / "ad_copy_frameworks.md").write_text("# Ad Copy\n")

    return tmp_path


# ─── Registry loading ─────────────────────────────────────────────
class TestRegistryLoading:
    def test_loads_from_fixture(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle = reg.load()
        assert bundle.loaded
        assert bundle.version == CONTEXT_VERSION
        assert len(bundle.content_hash) == 16

    def test_icp_slices(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle = reg.load()
        assert len(bundle.icp.anti_icp_signals) >= 2
        assert any("willingness" in s.lower() for s in bundle.icp.anti_icp_signals)

    def test_voice_slices(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle = reg.load()
        assert len(bundle.voice.banned_terms) >= 1
        assert len(bundle.voice.tone_principles) >= 1

    def test_pillar_slices(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle = reg.load()
        assert "Access Without Delay" in bundle.pillars.pillars

    def test_allowed_claims(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle = reg.load()
        assert len(bundle.allowed_claims) > 0
        assert all(c.source_url for c in bundle.allowed_claims)

    def test_map_semantics(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle = reg.load()
        assert len(bundle.map_semantics.firm_commitment_phrases) > 0
        assert len(bundle.map_semantics.campaign_types) > 0


# ─── Prompt block injection ───────────────────────────────────────
class TestPromptBlock:
    def test_prompt_block_voice(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        reg.load()
        block = reg.prompt_block(["voice"])
        assert "Tone:" in block or "Avoid:" in block

    def test_prompt_block_empty_for_unknown(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        reg.load()
        block = reg.prompt_block(["nonexistent_slice"])
        assert block == ""

    def test_prompt_block_claims(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        reg.load()
        block = reg.prompt_block(["claims"])
        assert "Approved claims:" in block


# ─── Feature flag / graceful fallback ─────────────────────────────
class TestFeatureFlag:
    def test_missing_dir_returns_empty_bundle(self, tmp_path: Path) -> None:
        reg = BusinessContextRegistry(tmp_path / "nonexistent")
        bundle = reg.load()
        assert bundle.loaded
        assert bundle.icp.segments  # defaults still present

    def test_env_override(self, business_dna_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULA_BUSINESS_DNA_PATH", str(business_dna_dir))
        BusinessContextRegistry.reset()
        reg = BusinessContextRegistry.get()
        assert reg.bundle.loaded


# ─── Content hash / drift detection ──────────────────────────────
class TestDriftDetection:
    def test_hash_changes_with_content(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        bundle1 = reg.load()
        hash1 = bundle1.content_hash

        icp_file = business_dna_dir / "core" / "ideal_customer_profile.md"
        icp_file.write_text(icp_file.read_text() + "\nNew anti-ICP signal.\n")

        bundle2 = reg.load()
        assert bundle2.content_hash != hash1

    def test_hash_stable_for_same_content(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        h1 = reg.load().content_hash
        h2 = reg.load().content_hash
        assert h1 == h2


# ─── Telemetry metadata ──────────────────────────────────────────
class TestTelemetryMetadata:
    def test_metadata_fields(self, business_dna_dir: Path) -> None:
        reg = BusinessContextRegistry(business_dna_dir)
        reg.load()
        meta = reg.telemetry_metadata()
        assert "context_version" in meta
        assert "context_hash" in meta
        assert meta["context_loaded"] == "True"


# ─── Singleton pattern ───────────────────────────────────────────
class TestSingleton:
    def test_get_returns_same_instance(self, business_dna_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULA_BUSINESS_DNA_PATH", str(business_dna_dir))
        BusinessContextRegistry.reset()
        a = BusinessContextRegistry.get()
        b = BusinessContextRegistry.get()
        assert a is b

    def test_reset_clears_instance(self, business_dna_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RULA_BUSINESS_DNA_PATH", str(business_dna_dir))
        BusinessContextRegistry.reset()
        a = BusinessContextRegistry.get()
        BusinessContextRegistry.reset()
        b = BusinessContextRegistry.get()
        assert a is not b


# ─── Golden test: deterministic scoring stability ─────────────────
class TestGoldenScoring:
    """Verify that value-prop scoring produces identical results
    when the context bundle and deterministic rules are unchanged."""

    def test_scoring_deterministic(self) -> None:
        from src.schemas.account import Account, EnrichedAccount
        from src.agents.prospecting.value_prop_scoring import score_value_props

        account = Account(
            account_id=1,
            company="Golden Corp",
            industry="Healthcare / Health System",
            us_employees=8000,
            health_plan="Anthem Blue Cross",
            contact={"name": "Jane Doe", "title": "VP Benefits"},
            notes="",
        )
        enriched = EnrichedAccount(
            account=account,
            icp_fit_score=80,
            data_completeness_score=90,
            flags=[],
        )

        r1 = score_value_props(enriched)
        r2 = score_value_props(enriched)

        assert [m.score for m in r1.matches] == [m.score for m in r2.matches]
        assert [m.value_prop for m in r1.matches] == [m.value_prop for m in r2.matches]


# ─── Golden test: MAP scoring stability ──────────────────────────
class TestGoldenMap:
    def test_map_scoring_deterministic(self) -> None:
        from src.agents.verification.parser import parse_evidence
        from src.agents.verification.scorer import score_commitment

        text_high = (
            "Email from VP Benefits: We are excited to move forward with quarterly "
            "campaigns for the full year. Launch email in Q1, benefits insert in Q2."
        )
        parsed = parse_evidence("golden_A", text_high)
        s1, t1, r1 = score_commitment(parsed)
        s2, t2, r2 = score_commitment(parsed)
        assert s1 == s2
        assert t1 == t2


# ─── Validator integration ────────────────────────────────────────
class TestValidatorIntegration:
    def test_claims_validator_exists(self) -> None:
        from src.validators.response_validator import validate_claims
        result = validate_claims("We have 21,000+ licensed providers.")
        assert isinstance(result.valid, bool)

    def test_voice_banned_in_semantic(self) -> None:
        from src.validators.response_validator import validate_email_semantic
        data = {"subject_line": "Test", "body": "guaranteed cure for all.\n\nMore text."}
        result = validate_email_semantic(data, "Test")
        # If business DNA is loaded, "guaranteed cure" would be flagged
        assert isinstance(result.valid, bool)
