"""Resolve employer-side committer name/title from evidence + optional company profile."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from src.config import load_config
from src.providers.base import GenerationRequest

if TYPE_CHECKING:
    from src.providers.router import ModelRouter

logger = logging.getLogger(__name__)

_SYSTEM = """You are extracting who at the employer/customer organization made or authorized the MAP commitment described in the evidence.
Return ONLY valid JSON with keys: name (string or null), title (string or null), rationale (short string).
Rules:
- name/title must refer to the employer-side person (not the AE, not Rula staff), unless the evidence only names the AE.
- If multiple people appear, pick the one who actually commits or speaks for the employer on the MAP/campaigns.
- Use the company profile only to disambiguate (e.g. first name + company name), not to invent people.
- If you cannot determine a person, use null for name and title."""


class CommitterExtraction(BaseModel):
    name: str | None = None
    title: str | None = None
    rationale: str | None = None
    source: Literal["llm", "heuristic"] = Field(default="heuristic")


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _heuristic_committer(evidence_text: str, company_profile: str) -> CommitterExtraction:
    text = evidence_text.strip()

    m = re.search(
        r"Email from\s+([^\n(]+?)\s*\(([^)]+)\)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return CommitterExtraction(
            name=m.group(1).strip(),
            title=m.group(2).strip(),
            rationale="pattern:email_from_name_title",
            source="heuristic",
        )

    m = re.search(r"Email from\s+([A-Za-z][A-Za-z\s,'.-]*?)\s+to\s+", text, re.IGNORECASE)
    if m:
        return CommitterExtraction(
            name=m.group(1).strip(),
            title=None,
            rationale="pattern:email_from_name_to",
            source="heuristic",
        )

    m = re.search(r"from\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*\(([^)]+)\)", text)
    if m and "email" in text.lower()[:80]:
        return CommitterExtraction(
            name=m.group(1).strip(),
            title=m.group(2).strip(),
            rationale="pattern:from_name_title",
            source="heuristic",
        )

    m = re.search(r"\b([A-Z][a-z]+)\s+mentioned\b", text)
    if m:
        return CommitterExtraction(
            name=m.group(1).strip(),
            title=None,
            rationale="pattern:firstname_mentioned",
            source="heuristic",
        )

    m = re.search(
        r"(?:phone|call)\s+with\s+([A-Z][a-z]+)\s+at\s+([A-Za-z]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        return CommitterExtraction(
            name=m.group(1).strip(),
            title=None,
            rationale="pattern:call_with_name_at_company",
            source="heuristic",
        )

    m = re.search(r"\b([A-Z][a-z]+)\s+at\s+([A-Z][a-z]+)\b", text)
    if m and ("slack" in text.lower() or "phone" in text.lower()):
        return CommitterExtraction(
            name=m.group(1).strip(),
            title=None,
            rationale="pattern:name_at_company",
            source="heuristic",
        )

    # Match profile contact name if evidence only says "She's in" / pronoun — weak signal
    if company_profile:
        cm = re.search(r"Primary contact on file:\s*([^(]+)\s*\(([^)]*)\)", company_profile)
        if cm and re.search(r"\bshe\b|\bhe\b|\bthey\b", text, re.IGNORECASE):
            n = cm.group(1).strip()
            t = cm.group(2).strip()
            if n and n != "—":
                return CommitterExtraction(
                    name=n,
                    title=t if t and t != "—" else None,
                    rationale="pattern:profile_disambiguation_pronoun",
                    source="heuristic",
                )

    return CommitterExtraction(source="heuristic")


def _parse_llm_json(raw: str) -> CommitterExtraction | None:
    try:
        data = json.loads(_strip_json_fence(raw))
        if not isinstance(data, dict):
            return None
        return CommitterExtraction(
            name=data.get("name") or None,
            title=data.get("title") or None,
            rationale=(data.get("rationale") or None) if isinstance(data.get("rationale"), str) else None,
            source="llm",
        )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug("committer LLM JSON parse failed: %s", e)
        return None


def resolve_committer(
    evidence_text: str,
    company_profile_markdown: str,
    *,
    router: ModelRouter | None = None,
) -> CommitterExtraction:
    """Try LLM JSON extraction, then merge with heuristics for missing name."""
    profile = (company_profile_markdown or "").strip()
    user_block = f"""## Evidence
{evidence_text.strip()}
"""
    if profile:
        user_block += f"\n## Company research profile (for disambiguation only)\n{profile}\n"

    cfg = load_config()
    r = router
    if r is None:
        from src.providers.router import ModelRouter

        r = ModelRouter(cfg)

    req = GenerationRequest(
        content_type="map_committer",
        system=_SYSTEM,
        prompt=user_block + '\nRespond with JSON only: {"name": string|null, "title": string|null, "rationale": string}',
        temperature=0.1,
        max_tokens=512,
    )
    resp = r.generate(req)
    out: CommitterExtraction | None = None
    if resp.ok and resp.text.strip():
        out = _parse_llm_json(resp.text)

    heur = _heuristic_committer(evidence_text, profile)

    if out and out.name:
        # Prefer LLM title if heuristic empty; keep LLM name
        title = out.title or heur.title
        return CommitterExtraction(
            name=out.name.strip(),
            title=title.strip() if title else None,
            rationale=out.rationale or heur.rationale,
            source="llm",
        )

    if heur.name:
        return heur

    if out and (out.name or out.title):
        return out

    return CommitterExtraction(name=None, title=None, rationale=None, source="heuristic")
