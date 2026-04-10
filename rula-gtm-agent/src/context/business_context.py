"""BusinessContextRegistry — typed context loader for the business dna corpus.

Truth-stack precedence (highest to lowest authority):
  1. Code invariants (schemas, sanitization, RBAC, kill switches, clamps)
  2. Deterministic rules (scoring, MAP tiers, evaluator thresholds)
  3. Structured context slices from business dna (this module)
  4. LLM-generated text (lowest; must pass validators)

This module produces bounded, typed slices — never raw full-file dumps.
Prompts and rules consume these slices; the LLM cannot override structured
pipeline outputs without the existing correction/audit path.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)

CONTEXT_VERSION = "v1.0"

_DEFAULT_BUSINESS_DNA_PATH = Path(__file__).resolve().parents[3] / "business dna"


def _env_context_path() -> Path:
    override = os.environ.get("RULA_BUSINESS_DNA_PATH", "")
    if override:
        return Path(override)
    return _DEFAULT_BUSINESS_DNA_PATH


def _read_md(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Business DNA file not found: %s", path)
    return ""


def _content_hash(texts: list[str]) -> str:
    h = hashlib.sha256()
    for t in sorted(texts):
        h.update(t.encode("utf-8"))
    return h.hexdigest()[:16]


def _extract_section(text: str, heading: str) -> str:
    """Extract a markdown section by heading (## level)."""
    pattern = rf"(?:^|\n)##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_table_rows(text: str) -> list[dict[str, str]]:
    """Parse markdown tables into list of dicts keyed by header columns."""
    rows: list[dict[str, str]] = []
    lines = [l.strip() for l in text.splitlines() if l.strip().startswith("|")]
    if len(lines) < 3:
        return rows
    headers = [c.strip() for c in lines[0].split("|") if c.strip()]
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


@dataclass(frozen=True)
class IcpConstraints:
    """Typed ICP slice for prospecting and MAP pipelines."""
    segments: list[str] = field(default_factory=list)
    anti_icp_signals: list[str] = field(default_factory=list)
    expansion_indicators: list[str] = field(default_factory=list)
    contraction_indicators: list[str] = field(default_factory=list)
    source_file: str = "core/ideal_customer_profile.md"


@dataclass(frozen=True)
class VoiceConstraints:
    """Banned terms, style rules, and tone guardrails from identity files."""
    banned_terms: list[str] = field(default_factory=list)
    preferred_terms: list[str] = field(default_factory=list)
    tone_principles: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PillarSummary:
    """Messaging pillar labels and descriptions for generation routing."""
    pillars: dict[str, str] = field(default_factory=dict)
    source_file: str = "identity/messaging_pillars.md"


@dataclass(frozen=True)
class AllowedClaim:
    """A single sourced claim approved for outbound use."""
    claim: str = ""
    source_url: str = ""
    category: str = ""


@dataclass(frozen=True)
class MapSemantics:
    """Commitment-language patterns and MAP assessment hints."""
    firm_commitment_phrases: list[str] = field(default_factory=list)
    soft_interest_phrases: list[str] = field(default_factory=list)
    campaign_types: list[str] = field(default_factory=list)
    source_file: str = "core/ideal_customer_profile.md"


@dataclass(frozen=True)
class ProductContext:
    """Core product framing for prompt augmentation."""
    value_prop_summary: str = ""
    care_types: list[str] = field(default_factory=list)
    differentiators: list[str] = field(default_factory=list)
    source_file: str = "core/product_dna.md"


@dataclass(frozen=True)
class CompetitorContext:
    """Category-level competitive framing for respectful positioning."""
    categories: list[str] = field(default_factory=list)
    positioning_rules: list[str] = field(default_factory=list)
    source_file: str = "core/competitor_landscape.md"


@dataclass
class ContextBundle:
    """Full context bundle with version and hash for telemetry binding."""
    version: str = CONTEXT_VERSION
    content_hash: str = ""
    icp: IcpConstraints = field(default_factory=IcpConstraints)
    voice: VoiceConstraints = field(default_factory=VoiceConstraints)
    pillars: PillarSummary = field(default_factory=PillarSummary)
    allowed_claims: list[AllowedClaim] = field(default_factory=list)
    map_semantics: MapSemantics = field(default_factory=MapSemantics)
    product: ProductContext = field(default_factory=ProductContext)
    competitor: CompetitorContext = field(default_factory=CompetitorContext)
    loaded: bool = False


class BusinessContextRegistry:
    """Singleton-style registry that loads and caches typed context slices."""

    _instance: ClassVar[BusinessContextRegistry | None] = None
    _bundle: ContextBundle

    def __init__(self, base_path: Path | None = None) -> None:
        self._base = base_path or _env_context_path()
        self._bundle = ContextBundle()
        self._raw_texts: dict[str, str] = {}

    @classmethod
    def get(cls) -> BusinessContextRegistry:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    @property
    def bundle(self) -> ContextBundle:
        return self._bundle

    def load(self) -> ContextBundle:
        """Parse all business dna files into typed slices."""
        files = {
            "business_context": self._base / "core" / "business_context.md",
            "icp": self._base / "core" / "ideal_customer_profile.md",
            "product_dna": self._base / "core" / "product_dna.md",
            "competitor": self._base / "core" / "competitor_landscape.md",
            "pillars": self._base / "identity" / "messaging_pillars.md",
            "voice": self._base / "identity" / "brand_voice_matrix.md",
            "style": self._base / "identity" / "style_guides.md",
            "ad_copy": self._base / "identity" / "ad_copy_frameworks.md",
        }
        self._raw_texts = {k: _read_md(v) for k, v in files.items()}
        content_hash = _content_hash(list(self._raw_texts.values()))

        self._bundle = ContextBundle(
            version=CONTEXT_VERSION,
            content_hash=content_hash,
            icp=self._parse_icp(),
            voice=self._parse_voice(),
            pillars=self._parse_pillars(),
            allowed_claims=self._parse_claims(),
            map_semantics=self._parse_map_semantics(),
            product=self._parse_product(),
            competitor=self._parse_competitor(),
            loaded=True,
        )
        logger.info(
            "Business context loaded: version=%s hash=%s",
            self._bundle.version,
            self._bundle.content_hash,
        )
        return self._bundle

    def _parse_icp(self) -> IcpConstraints:
        raw = self._raw_texts.get("icp", "")
        segments = ["health_system", "university", "large_commercial_employer"]

        anti_signals = []
        anti_section = _extract_section(raw, r"9\.\s*Anti-ICP")
        if not anti_section:
            anti_section = _extract_section(raw, "Anti-ICP")
        for line in anti_section.splitlines():
            line = line.strip().lstrip("-").strip()
            if line:
                anti_signals.append(line)

        expansion = []
        exp_section = _extract_section(raw, r"5\.\s*Expansion")
        if not exp_section:
            exp_section = _extract_section(raw, "Expansion/Contraction Signals")
        for line in exp_section.splitlines():
            if line.strip().startswith("- ") and "expansion" in line.lower() or "multi-quarter" in line.lower():
                expansion.append(line.strip().lstrip("-").strip())

        contraction = []
        for line in exp_section.splitlines():
            if line.strip().startswith("- ") and ("contraction" in line.lower() or "vague" in line.lower() or "single" in line.lower()):
                contraction.append(line.strip().lstrip("-").strip())

        return IcpConstraints(
            segments=segments,
            anti_icp_signals=anti_signals or [
                "Organizations with low campaign-operating willingness.",
                "Contacts without decision authority and no path to authority.",
                "Cases where benefits channel access is blocked or unverifiable.",
            ],
            expansion_indicators=expansion or [
                "Multi-quarter campaign commitment.",
                "Added campaign modalities.",
                "Stakeholder broadening beyond a single champion.",
            ],
            contraction_indicators=contraction or [
                "Vague intent language without timeline.",
                "Single-channel, one-off campaign proposals.",
                "No confirmation from benefits decision-maker.",
            ],
        )

    def _parse_voice(self) -> VoiceConstraints:
        voice_raw = self._raw_texts.get("voice", "")
        style_raw = self._raw_texts.get("style", "")

        banned = []
        avoid_section = _extract_section(voice_raw, r"4\.\s*Vocabulary")
        if not avoid_section:
            avoid_section = _extract_section(voice_raw, "Vocabulary & Diction")
        for line in avoid_section.splitlines():
            if "avoid" in line.lower():
                for sub in avoid_section.splitlines()[avoid_section.splitlines().index(line) + 1:]:
                    sub = sub.strip().lstrip("-").strip().strip('"').strip("'")
                    if sub and not sub.startswith("#"):
                        banned.append(sub.lower())
                break
        if not banned:
            banned = [
                "stigmatizing labels", "unsourced superlatives",
                "aggressive competitor put-downs", "guaranteed cure",
            ]

        preferred = [
            "in-network care", "provider match", "mental well-being",
            "therapy and psychiatry", "coverage verified",
            "personalized treatment plan", "access", "progress",
        ]

        principles = []
        personality = _extract_section(voice_raw, r"1\.\s*The Core Personality")
        if not personality:
            personality = _extract_section(voice_raw, "Core Personality")
        for line in personality.splitlines():
            line = line.strip().lstrip("-*").strip()
            if line and ":" in line:
                principles.append(line)
        if not principles:
            principles = [
                "Compassionate, Clear, Credible",
                "No fear/stigma framing",
                "No absolute clinical guarantees",
            ]

        return VoiceConstraints(
            banned_terms=banned,
            preferred_terms=preferred,
            tone_principles=principles,
            source_files=["identity/brand_voice_matrix.md", "identity/style_guides.md"],
        )

    def _parse_pillars(self) -> PillarSummary:
        raw = self._raw_texts.get("pillars", "")
        pillars: dict[str, str] = {}
        current_key = ""
        for line in raw.splitlines():
            if line.startswith("### Pillar"):
                m = re.search(r"Pillar\s*\d+:\s*(.+)", line)
                if m:
                    current_key = m.group(1).strip()
            elif current_key and line.strip().startswith("- **Core argument:**"):
                pillars[current_key] = line.split(":**", 1)[-1].strip()
                current_key = ""

        if not pillars:
            pillars = {
                "Access Without Delay": "Fast in-network care matching.",
                "Insurance Simplicity": "Clear costs before treatment.",
                "Progress-Oriented Care": "Measurable clinical improvement.",
                "Integrated Journey": "Therapy + psychiatry coordination.",
                "Partner-Ready Infrastructure": "Scalable employer/plan/system value.",
                "Source-Backed Discipline": "Claims must be current and sourced.",
            }
        return PillarSummary(pillars=pillars)

    def _parse_claims(self) -> list[AllowedClaim]:
        raw = self._raw_texts.get("business_context", "")
        claims = [
            AllowedClaim("21,000+ licensed providers", "https://www.rula.com/", "network"),
            AllowedClaim("180+ clinical specialties and modalities", "https://www.rula.com/", "network"),
            AllowedClaim("170M+ individuals covered by insurance", "https://www.rula.com/", "coverage"),
            AllowedClaim("Typical insured session cost ~$15", "https://www.rula.com/how-much-does-therapy-cost/", "affordability"),
            AllowedClaim("98% find a provider matching preferences", "https://www.rula.com/", "matching"),
            AllowedClaim("93% report feeling better", "https://www.rula.com/", "outcomes"),
            AllowedClaim("76% meaningful improvement within 8 sessions", "https://www.rula.com/partnerships-employers/", "outcomes"),
            AllowedClaim("5M+ successful sessions completed", "https://www.rula.com/partnerships-employers/", "scale"),
            AllowedClaim("Appointments available as soon as tomorrow", "https://www.rula.com/online-therapy/", "access"),
            AllowedClaim("100+ insurance plans accepted", "https://www.rula.com/how-much-does-therapy-cost/", "coverage"),
        ]
        return claims

    def _parse_map_semantics(self) -> MapSemantics:
        raw = self._raw_texts.get("icp", "")
        return MapSemantics(
            firm_commitment_phrases=[
                "excited to move forward", "we'd like to plan",
                "commit to quarterly campaigns", "launch in",
                "we're in", "send the map doc",
            ],
            soft_interest_phrases=[
                "exploring", "no commitment", "at the earliest",
                "need to get buy-in", "looking at", "interested in",
            ],
            campaign_types=[
                "launch_email", "benefits_insert", "manager_toolkit",
                "quarterly_campaign", "email_blast", "posters",
            ],
        )

    def _parse_product(self) -> ProductContext:
        raw = self._raw_texts.get("product_dna", "")
        summary = _extract_section(raw, r"1\.\s*Value Proposition")
        if not summary:
            summary = _extract_section(raw, "Value Proposition")

        return ProductContext(
            value_prop_summary=summary[:500] if summary else (
                "Find in-network mental healthcare that fits your needs quickly, "
                "with clear cost expectations and flexible care formats."
            ),
            care_types=["individual therapy", "couples therapy", "family therapy",
                        "child therapy", "teen therapy", "psychiatry", "medication management"],
            differentiators=[
                "Insurance-first design",
                "Large in-network provider network",
                "Integrated therapy + psychiatry",
                "Partnership-grade operating model",
            ],
        )

    def _parse_competitor(self) -> CompetitorContext:
        raw = self._raw_texts.get("competitor", "")
        return CompetitorContext(
            categories=[
                "digital mental health marketplaces",
                "provider directory alternatives",
                "traditional fragmented local options",
                "EAP status-quo",
                "in-house behavioral health capacity",
                "generic telehealth platforms",
            ],
            positioning_rules=[
                "Respectful comparison only; no competitor attacks.",
                "Emphasize fit, workflow friction, and outcomes.",
                "Avoid unsupported superlatives.",
            ],
        )

    def prompt_block(self, slices: list[str]) -> str:
        """Build a bounded context block for prompt injection.

        Only includes requested slices, never the full corpus.
        """
        parts: list[str] = []
        b = self._bundle

        if "voice" in slices and b.voice.tone_principles:
            parts.append("Tone: " + "; ".join(b.voice.tone_principles[:3]))
            if b.voice.banned_terms:
                parts.append("Avoid: " + ", ".join(b.voice.banned_terms[:6]))

        if "pillars" in slices and b.pillars.pillars:
            pillar_lines = [f"- {k}: {v}" for k, v in list(b.pillars.pillars.items())[:4]]
            parts.append("Messaging pillars:\n" + "\n".join(pillar_lines))

        if "claims" in slices and b.allowed_claims:
            claim_lines = [f"- {c.claim} (source: {c.source_url})" for c in b.allowed_claims[:5]]
            parts.append("Approved claims:\n" + "\n".join(claim_lines))

        if "product" in slices:
            parts.append(f"Product: {b.product.value_prop_summary[:200]}")

        if "icp" in slices and b.icp.segments:
            parts.append("ICP segments: " + ", ".join(b.icp.segments))

        if "competitor" in slices and b.competitor.positioning_rules:
            parts.append("Competitor rules: " + "; ".join(b.competitor.positioning_rules[:2]))

        return "\n\n".join(parts) if parts else ""

    def telemetry_metadata(self) -> dict[str, str]:
        return {
            "context_version": self._bundle.version,
            "context_hash": self._bundle.content_hash,
            "context_loaded": str(self._bundle.loaded),
        }
