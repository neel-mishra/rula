"""Company context retrieval: LinkedIn-first, news fallback.

Provides the [Company_Context] variable for Stage 4 email/question generation.
Returns structured context with source attribution and confidence flags.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from src.integrations.connector_policy import CONTEXT_COMPANY, get_connector_policy

logger = logging.getLogger(__name__)

CONTEXT_TIMEOUT_SECONDS = float(get_connector_policy(CONTEXT_COMPANY).timeout_seconds)


@dataclass
class CompanyContext:
    source_type: str  # "linkedin" | "news" | "none"
    source_url: str = ""
    context_snippet: str = ""
    retrieved_at: float = field(default_factory=time.time)
    confidence: str = "none"  # "high" | "medium" | "low" | "none"
    flags: list[str] = field(default_factory=list)


def _try_linkedin_context(prospect_name: str) -> CompanyContext | None:
    """Attempt to retrieve recent LinkedIn post from prospect.

    In production this would:
    1. Search "{prospect_name} linkedin"
    2. Navigate to profile
    3. Scan posts for business-relevant content using business DNA context
    4. Return the most relevant snippet

    Currently returns None (placeholder) unless a web-scraping integration
    is configured. The pipeline gracefully falls back to news.
    """
    logger.info("LinkedIn context lookup for: %s (placeholder)", prospect_name)
    return None


def _try_news_context(company_name: str) -> CompanyContext | None:
    """Attempt to retrieve recent company news.

    In production this would:
    1. Search "{company_name} recent news"
    2. Filter for hiring, workforce, benefits, or business-model-relevant events
    3. Return the most relevant snippet with source URL

    Currently returns None (placeholder). The pipeline will generate
    with a MISSING_CONTEXT flag.
    """
    logger.info("News context lookup for: %s (placeholder)", company_name)
    return None


def fetch_company_context(
    prospect_name: str,
    company_name: str,
    *,
    timeout: float | None = None,
) -> CompanyContext:
    """LinkedIn-first, news-fallback context retrieval.

    Returns a CompanyContext with explicit flags when no context is available.
    Never raises -- fail-closed with flags instead.
    """
    if timeout is None:
        timeout = float(get_connector_policy(CONTEXT_COMPANY).timeout_seconds)
    t0 = time.monotonic()

    try:
        ctx = _try_linkedin_context(prospect_name)
        if ctx and ctx.context_snippet:
            ctx.confidence = "high"
            return ctx
    except Exception as e:
        logger.warning("LinkedIn context fetch failed: %s", e)

    elapsed = time.monotonic() - t0
    remaining = timeout - elapsed
    if remaining <= 0:
        return CompanyContext(
            source_type="none",
            confidence="none",
            flags=["MISSING_CONTEXT", "TIMEOUT_LINKEDIN"],
        )

    try:
        ctx = _try_news_context(company_name)
        if ctx and ctx.context_snippet:
            ctx.confidence = "medium"
            return ctx
    except Exception as e:
        logger.warning("News context fetch failed: %s", e)

    ctx = CompanyContext(
        source_type="none",
        confidence="none",
        flags=["MISSING_CONTEXT"],
    )

    try:
        from src.context.business_context import BusinessContextRegistry
        reg = BusinessContextRegistry.get()
        if reg.bundle.loaded and not ctx.context_snippet:
            ctx.flags.append("BUSINESS_DNA_AVAILABLE")
    except Exception:
        pass

    return ctx
