from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)


def _voice_banned_terms() -> list[str]:
    """Load banned terms from business DNA voice constraints."""
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            return reg.bundle.voice.banned_terms
    except Exception:
        pass
    return []


def _allowed_claim_texts() -> list[str]:
    """Load approved claim strings from business DNA."""
    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded:
            return [c.claim.lower() for c in reg.bundle.allowed_claims]
    except Exception:
        pass
    return []


def validate_email_json(raw: str) -> ValidationResult:
    issues: list[str] = []
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
    except json.JSONDecodeError:
        return ValidationResult(valid=False, issues=["Not valid JSON"])

    if not isinstance(data, dict):
        return ValidationResult(valid=False, issues=["Expected JSON object"])

    for key in ("subject_line", "body"):
        if key not in data:
            issues.append(f"Missing required field: {key}")
        elif not isinstance(data[key], str):
            issues.append(f"Field '{key}' must be a string")
    subj = data.get("subject_line")
    body = data.get("body")
    if isinstance(subj, str) and len(subj) > 100:
        issues.append("Subject line exceeds 100 chars")
    if isinstance(body, str) and len(body) < 20:
        issues.append("Body too short (< 20 chars)")
    if isinstance(body, str) and "!" in body:
        issues.append("Body contains exclamation mark (style violation)")

    return ValidationResult(valid=len(issues) == 0, issues=issues)


def validate_questions_json(raw: str) -> ValidationResult:
    issues: list[str] = []
    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(text)
    except json.JSONDecodeError:
        return ValidationResult(valid=False, issues=["Not valid JSON"])

    if not isinstance(data, list):
        return ValidationResult(valid=False, issues=["Expected JSON array"])
    if len(data) < 2:
        issues.append("Fewer than 2 questions")
    for i, q in enumerate(data):
        if not isinstance(q, str):
            issues.append(f"Item {i} is not a string")
        elif not q.strip().endswith("?"):
            issues.append(f"Item {i} doesn't end with '?'")

    return ValidationResult(valid=len(issues) == 0, issues=issues)


def validate_email_semantic(
    email_data: dict,
    company_name: str,
) -> ValidationResult:
    issues: list[str] = []
    subject = email_data.get("subject_line", "")
    body = email_data.get("body", "")
    combined = (subject + " " + body).lower()
    if company_name.lower() not in combined:
        issues.append(f"Company name '{company_name}' not mentioned")
    if "exciting" in combined:
        issues.append("Contains prohibited word 'exciting'")
    if body.count("\n\n") < 1:
        issues.append("Body has fewer than 2 paragraphs")

    for term in _voice_banned_terms():
        if term.lower() in combined:
            issues.append(f"Voice constraint: banned term '{term}'")

    return ValidationResult(valid=len(issues) == 0, issues=issues)


def validate_claims(text: str) -> ValidationResult:
    """Check that numeric claims in generated text match the allowlist.

    Extracts patterns like "X% ...", "X,XXX ...", "X+ ..." and verifies
    they appear in the approved claims from business DNA. Unknown numeric
    claims cause validation to fail (valid=False).
    """
    issues: list[str] = []
    allowed = _allowed_claim_texts()
    if not allowed:
        return ValidationResult(valid=True, issues=[])

    numeric_patterns = re.findall(r'\b\d[\d,.]*[+%]?\s+\w+', text)
    for pattern in numeric_patterns:
        normalized = pattern.strip().lower()
        if not any(normalized[:15] in claim for claim in allowed):
            issues.append(f"Unsourced numeric claim: '{pattern.strip()[:50]}'")

    return ValidationResult(valid=len(issues) == 0, issues=issues)
