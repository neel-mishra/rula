"""
Token budget enforcement — per-mailbox daily cap and user-level monthly cap.

Uses Redis to track cumulative token usage. When budget is exceeded, raises
BudgetExhaustedError so callers can degrade gracefully (deterministic-only mode).

USD cost accounting piggybacks on the same call path: `record_usage_usd`
multiplies token counts by a per-model price table and tracks daily totals
for later SLO / cost-per-inbox rollups.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
import redis.asyncio as aioredis

from core.config import settings

log = structlog.get_logger(__name__)

_redis: aioredis.Redis | None = None

# Key patterns
_DAILY_KEY = "budget:daily:{mailbox_id}:{date}"
_MONTHLY_KEY = "budget:monthly:{date}"
_COST_DAILY_KEY = "cost:daily:{date}"                     # total USD cents across all mailboxes
_COST_MAILBOX_DAILY_KEY = "cost:mailbox:{mailbox_id}:{date}"  # per-mailbox USD cents
_COST_TTL_SECONDS = 40 * 86400                            # keep >=30d for SLO windows


# USD price per 1K tokens. Add new entries as models are added. A miss falls
# back to _DEFAULT_PRICE so cost accounting never silently zeroes out.
# Sources: Anthropic + OpenAI published rate cards (per 1K tokens).
PRICING_USD_PER_1K: dict[str, tuple[float, float]] = {
    # Claude family
    "claude-opus-4-7": (0.015, 0.075),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5-20251001": (0.001, 0.005),
    "claude-haiku-4-5": (0.001, 0.005),
    # OpenAI family
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    # Embeddings (output tokens always 0)
    "text-embedding-3-small": (0.00002, 0.0),
    "text-embedding-3-large": (0.00013, 0.0),
}

_DEFAULT_PRICE = (0.005, 0.015)   # conservative, middle-of-the-road


class BudgetExhaustedError(Exception):
    """Raised when a mailbox or user exceeds their token budget."""

    def __init__(self, scope: str, used: int, limit: int) -> None:
        self.scope = scope
        self.used = used
        self.limit = limit
        super().__init__(f"Token budget exhausted ({scope}): {used}/{limit}")


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _cents_to_tokens(cents: int) -> int:
    """
    Rough conversion: 1 cent ≈ 10,000 tokens (based on typical pricing).
    This is a configurable heuristic; exact cost accounting happens in telemetry.
    """
    return cents * 10_000


async def check_budget(mailbox_id: str) -> None:
    """
    Check if the mailbox and user are within budget. Raises BudgetExhaustedError if not.
    Call before every LLM request.
    """
    r = await _get_redis()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")

    # Per-mailbox daily budget
    daily_key = _DAILY_KEY.format(mailbox_id=mailbox_id, date=today)
    daily_used = int(await r.get(daily_key) or 0)
    daily_limit = _cents_to_tokens(settings.llm_daily_budget_cents_per_mailbox)

    if daily_used >= daily_limit:
        log.warning("budget.daily_exhausted", mailbox_id=mailbox_id, used=daily_used, limit=daily_limit)
        raise BudgetExhaustedError("daily_mailbox", daily_used, daily_limit)

    # User-level monthly budget
    monthly_key = _MONTHLY_KEY.format(date=month)
    monthly_used = int(await r.get(monthly_key) or 0)
    monthly_limit = _cents_to_tokens(settings.llm_monthly_budget_cents)

    # Auto-degradation at threshold
    degradation_limit = int(monthly_limit * settings.llm_budget_degradation_threshold)
    if monthly_used >= degradation_limit:
        log.warning("budget.degradation_threshold", used=monthly_used, threshold=degradation_limit)
        raise BudgetExhaustedError("monthly_degradation", monthly_used, degradation_limit)


async def record_usage(mailbox_id: str, input_tokens: int, output_tokens: int) -> None:
    """Record token usage after a successful LLM call."""
    r = await _get_redis()
    total = input_tokens + output_tokens
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")

    daily_key = _DAILY_KEY.format(mailbox_id=mailbox_id, date=today)
    monthly_key = _MONTHLY_KEY.format(date=month)

    pipe = r.pipeline()
    pipe.incrby(daily_key, total)
    pipe.expire(daily_key, 86400 * 2)  # TTL: 2 days
    pipe.incrby(monthly_key, total)
    pipe.expire(monthly_key, 86400 * 35)  # TTL: 35 days
    await pipe.execute()


def compute_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for a single call given the model + token counts."""
    price_in, price_out = PRICING_USD_PER_1K.get(model_id, _DEFAULT_PRICE)
    return (input_tokens / 1000.0) * price_in + (output_tokens / 1000.0) * price_out


async def record_usage_usd(
    mailbox_id: str | None,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Track USD cost in micro-cents per day (global + per-mailbox).

    Returns the computed cost in USD for this call (so callers can log it).
    Micro-cents = 10_000 per dollar; integer math keeps Redis counters exact.
    Never raises: Redis failure is logged and swallowed.
    """
    cost_usd = compute_cost_usd(model_id, input_tokens, output_tokens)
    micro_cents = int(round(cost_usd * 10_000))
    if micro_cents <= 0:
        return cost_usd
    try:
        r = await _get_redis()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        pipe = r.pipeline()
        daily_key = _COST_DAILY_KEY.format(date=today)
        pipe.incrby(daily_key, micro_cents)
        pipe.expire(daily_key, _COST_TTL_SECONDS)
        if mailbox_id:
            mb_key = _COST_MAILBOX_DAILY_KEY.format(
                mailbox_id=mailbox_id, date=today
            )
            pipe.incrby(mb_key, micro_cents)
            pipe.expire(mb_key, _COST_TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        log.warning("budget.cost_record_failed", error=str(exc))
    return cost_usd


async def get_cost_totals(window_days: int = 7) -> dict:
    """
    Aggregate daily USD cost over the last `window_days`.

    Returns:
        total_usd: sum over the window
        per_day: list of {date, usd}
        active_mailbox_days: number of (mailbox, day) pairs with any cost
            — the denominator for "cost per active inbox per day".
    """
    total_micro_cents = 0
    active_mailbox_days = 0
    per_day: list[dict] = []
    try:
        r = await _get_redis()
        today = datetime.now(tz=timezone.utc).date()
        # Global daily totals
        pipe = r.pipeline()
        for offset in range(window_days):
            date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            pipe.get(_COST_DAILY_KEY.format(date=date))
        daily_values = await pipe.execute()
        for offset, raw in enumerate(daily_values):
            date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            mc = int(raw or 0)
            total_micro_cents += mc
            per_day.append({"date": date, "usd": mc / 10_000.0})

        # Active-mailbox-days = count of per-mailbox keys in the window
        for offset in range(window_days):
            date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            pattern = _COST_MAILBOX_DAILY_KEY.format(mailbox_id="*", date=date)
            matched = 0
            async for _ in r.scan_iter(match=pattern, count=100):
                matched += 1
            active_mailbox_days += matched
        await r.aclose()
    except Exception as exc:
        log.warning("budget.cost_rollup_failed", error=str(exc))
        return {
            "total_usd": 0.0,
            "per_day": [],
            "active_mailbox_days": 0,
            "cost_per_active_mailbox_day": None,
        }

    total_usd = total_micro_cents / 10_000.0
    avg = (
        total_usd / active_mailbox_days if active_mailbox_days else None
    )
    return {
        "total_usd": total_usd,
        "per_day": per_day,
        "active_mailbox_days": active_mailbox_days,
        "cost_per_active_mailbox_day": avg,
    }


async def get_usage(mailbox_id: str) -> dict:
    """Get current budget status for a mailbox."""
    r = await _get_redis()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(tz=timezone.utc).strftime("%Y-%m")

    daily_key = _DAILY_KEY.format(mailbox_id=mailbox_id, date=today)
    monthly_key = _MONTHLY_KEY.format(date=month)

    daily_used = int(await r.get(daily_key) or 0)
    monthly_used = int(await r.get(monthly_key) or 0)

    return {
        "daily_used": daily_used,
        "daily_limit": _cents_to_tokens(settings.llm_daily_budget_cents_per_mailbox),
        "monthly_used": monthly_used,
        "monthly_limit": _cents_to_tokens(settings.llm_monthly_budget_cents),
    }
