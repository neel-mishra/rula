"""
Per-mailbox Gmail API rate limiter.

Gmail API quotas are per-user (per connected Google account).
Uses Redis sliding window to prevent hitting Gmail rate limits
and ensure one hot mailbox doesn't starve others.
"""

from __future__ import annotations

import time

import structlog
import redis.asyncio as aioredis

from core.config import settings

log = structlog.get_logger(__name__)

# Gmail API default: 250 quota units per second per user
# Most read operations = 5 units, modify = 10 units
_DEFAULT_MAX_CALLS_PER_SECOND = 25  # conservative: ~125 quota units/sec
_DEFAULT_MAX_CALLS_PER_MINUTE = 500
_WINDOW_KEY = "ratelimit:gmail:{mailbox_id}:{window}"

_redis: aioredis.Redis | None = None


class GmailRateLimitError(Exception):
    """Raised when a mailbox exceeds its Gmail API rate limit."""

    def __init__(self, mailbox_id: str, window: str) -> None:
        self.mailbox_id = mailbox_id
        self.window = window
        super().__init__(f"Gmail rate limit exceeded for mailbox {mailbox_id} ({window})")


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def check_gmail_rate_limit(
    mailbox_id: str,
    max_per_second: int = _DEFAULT_MAX_CALLS_PER_SECOND,
    max_per_minute: int = _DEFAULT_MAX_CALLS_PER_MINUTE,
) -> None:
    """
    Check if the mailbox is within Gmail API rate limits.
    Raises GmailRateLimitError if exceeded.
    """
    r = await _get_redis()
    now = int(time.time())

    # Per-second window
    sec_key = _WINDOW_KEY.format(mailbox_id=mailbox_id, window=f"sec:{now}")
    sec_count = int(await r.get(sec_key) or 0)
    if sec_count >= max_per_second:
        raise GmailRateLimitError(mailbox_id, "per_second")

    # Per-minute window
    minute = now // 60
    min_key = _WINDOW_KEY.format(mailbox_id=mailbox_id, window=f"min:{minute}")
    min_count = int(await r.get(min_key) or 0)
    if min_count >= max_per_minute:
        raise GmailRateLimitError(mailbox_id, "per_minute")


async def record_gmail_call(mailbox_id: str) -> None:
    """Record a Gmail API call for rate limiting."""
    r = await _get_redis()
    now = int(time.time())
    minute = now // 60

    pipe = r.pipeline()

    sec_key = _WINDOW_KEY.format(mailbox_id=mailbox_id, window=f"sec:{now}")
    pipe.incr(sec_key)
    pipe.expire(sec_key, 2)

    min_key = _WINDOW_KEY.format(mailbox_id=mailbox_id, window=f"min:{minute}")
    pipe.incr(min_key)
    pipe.expire(min_key, 120)

    await pipe.execute()
