"""
CSRF state management for OAuth flows.

Stores OAuth state tokens in Redis with a short TTL.
Validates state on callback to prevent CSRF attacks.
"""

from __future__ import annotations

import secrets
from typing import Any

import redis.asyncio as aioredis

from core.config import settings

_STATE_PREFIX = "oauth_state:"
_STATE_TTL_SECONDS = 600  # 10 minutes

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def generate_oauth_state(user_id: str | None = None) -> str:
    """Generate a cryptographic state token and store it in Redis."""
    state = secrets.token_urlsafe(32)
    r = await _get_redis()
    value = user_id or "anonymous"
    await r.set(f"{_STATE_PREFIX}{state}", value, ex=_STATE_TTL_SECONDS)
    return state


async def validate_oauth_state(state: str) -> str | None:
    """
    Validate and consume a state token. Returns the stored user_id (or
    'anonymous') if valid, None if missing/expired. Token is deleted
    after validation to prevent replay.
    """
    r = await _get_redis()
    key = f"{_STATE_PREFIX}{state}"
    value = await r.get(key)
    if value is not None:
        await r.delete(key)
    return value


async def close_redis() -> None:
    """Graceful shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
