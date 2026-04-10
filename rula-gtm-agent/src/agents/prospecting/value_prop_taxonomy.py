"""Industry, health-plan, and context-phrase normalization for value-prop scoring.

Provides alias dictionaries and normalizers so upstream scoring is resilient
to variations in ingested data (e.g. "Healthcare" vs "Health System").
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Industry ontology  (canonical segment -> aliases)
# ---------------------------------------------------------------------------
INDUSTRY_ALIASES: dict[str, list[str]] = {
    "health_system": [
        "health", "healthcare", "health system", "health services",
        "hospital", "provider", "medical", "clinical",
    ],
    "university": [
        "university", "education", "higher-ed", "higher ed",
        "college", "academic", "school",
    ],
    "senior_living": [
        "senior", "living", "assisted living", "nursing",
        "long-term care", "ltc", "elder",
    ],
    "financial": [
        "financial", "banking", "insurance", "fintech", "finance",
    ],
    "transportation": [
        "transport", "logistics", "shipping", "freight", "trucking",
    ],
    "natural_resources": [
        "forestry", "natural", "mining", "agriculture", "energy",
    ],
}


def normalize_industry(raw: str) -> str:
    """Return canonical segment key, or 'other' if unrecognized."""
    lower = raw.lower().strip()
    for canonical, aliases in INDUSTRY_ALIASES.items():
        for alias in aliases:
            if alias in lower:
                return canonical
    return "other"


# ---------------------------------------------------------------------------
# Health-plan alias resolver
# ---------------------------------------------------------------------------
CARRIER_FAMILIES: dict[str, list[str]] = {
    "anthem": ["anthem", "elevance", "wellpoint"],
    "aetna": ["aetna", "cvs health"],
    "cigna": ["cigna", "evernorth"],
    "bcbs": ["bcbs", "blue cross", "blue shield"],
    "united": ["united", "uhc", "optum"],
    "kaiser": ["kaiser"],
    "humana": ["humana"],
}

PRIORITY_CARRIERS = {"anthem", "aetna", "cigna", "bcbs", "united"}


def normalize_health_plan(raw: str | None) -> tuple[str, str]:
    """Return (canonical_carrier, carrier_family).

    Returns ("unknown", "unknown") when input is missing/unrecognized.
    """
    if not raw or raw.lower().strip() in {"", "unknown", "n/a", "none"}:
        return ("unknown", "unknown")
    lower = raw.lower().strip()
    for family, aliases in CARRIER_FAMILIES.items():
        for alias in aliases:
            if alias in lower:
                return (raw.strip(), family)
    return (raw.strip(), "other")


# ---------------------------------------------------------------------------
# Context-phrase dictionaries (notes / news signal buckets)
# ---------------------------------------------------------------------------
PHRASE_SIGNALS: dict[str, dict[str, str]] = {
    "turnover": {"bucket": "workforce_productivity", "polarity": "positive"},
    "24/7": {"bucket": "workforce_productivity", "polarity": "positive"},
    "shift-based": {"bucket": "workforce_productivity", "polarity": "positive"},
    "eap": {"bucket": "eap_upgrade", "polarity": "positive"},
    "wellness": {"bucket": "eap_upgrade", "polarity": "positive"},
    "limited internet": {"bucket": "employee_access", "polarity": "positive"},
    "field-based": {"bucket": "employee_access", "polarity": "positive"},
    "remote workforce": {"bucket": "employee_access", "polarity": "positive"},
    "merger": {"bucket": "total_cost_of_care", "polarity": "positive"},
    "integrating": {"bucket": "total_cost_of_care", "polarity": "positive"},
    "cost containment": {"bucket": "total_cost_of_care", "polarity": "positive"},
    "no contact": {"bucket": "_negative", "polarity": "risk"},
    "already optimized": {"bucket": "_contradiction", "polarity": "contradiction"},
}


def extract_context_signals(text: str) -> list[dict[str, str]]:
    """Scan free-text for known phrase signals.

    Returns list of dicts: {phrase, bucket, polarity, matched_text}.
    """
    lower = text.lower()
    hits: list[dict[str, str]] = []
    for phrase, meta in PHRASE_SIGNALS.items():
        if phrase in lower:
            hits.append({
                "phrase": phrase,
                "bucket": meta["bucket"],
                "polarity": meta["polarity"],
                "matched_text": phrase,
            })
    return hits
