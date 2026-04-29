"""
LLM response and embedding cache — Redis-backed with TTL.
Cache key includes prompt hash + model to prevent cross-model contamination.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from core.config import settings

log = structlog.get_logger(__name__)

LLM_CACHE_TTL = 3600 * 24  # 24 hours
EMBEDDING_CACHE_TTL = 3600 * 24 * 7  # 7 days

# Daily counters have a 40-day TTL so the 30-day SLO window always sees data
_COUNTER_TTL_SECONDS = 40 * 86400

# Counter key shape: slo:cache:{result}:{prefix}:{YYYY-MM-DD}
#   result = "hit" | "miss"
#   prefix = "llm" | "emb"
_COUNTER_KEY = "slo:cache:{result}:{prefix}:{date}"


def _cache_key(prefix: str, model: str, text: str) -> str:
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:24]
    return f"cache:{prefix}:{model}:{text_hash}"


async def _get_redis():
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def _incr_counter(result: str, prefix: str) -> None:
    """Best-effort per-day counter increment. Never raises."""
    try:
        r = await _get_redis()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        key = _COUNTER_KEY.format(result=result, prefix=prefix, date=today)
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _COUNTER_TTL_SECONDS)
        await pipe.execute()
        await r.aclose()
    except Exception:
        pass


async def get_cached_completion(model: str, system: str, user: str) -> dict | None:
    """Check cache for a previous LLM response."""
    try:
        r = await _get_redis()
        key = _cache_key("llm", model, system + "|" + user)
        cached = await r.get(key)
        await r.aclose()
        if cached:
            log.debug("cache.llm_hit", key=key[:40])
            await _incr_counter("hit", "llm")
            return json.loads(cached)
    except Exception:
        return None
    await _incr_counter("miss", "llm")
    return None


async def set_cached_completion(
    model: str, system: str, user: str, response_data: dict
) -> None:
    """Store an LLM response in cache."""
    try:
        r = await _get_redis()
        key = _cache_key("llm", model, system + "|" + user)
        await r.setex(key, LLM_CACHE_TTL, json.dumps(response_data))
        await r.aclose()
    except Exception:
        pass


async def get_cached_embedding(model: str, text: str) -> list[float] | None:
    """Check cache for a previous embedding."""
    try:
        r = await _get_redis()
        key = _cache_key("emb", model, text)
        cached = await r.get(key)
        await r.aclose()
        if cached:
            log.debug("cache.embedding_hit", key=key[:40])
            await _incr_counter("hit", "emb")
            return json.loads(cached)
    except Exception:
        return None
    await _incr_counter("miss", "emb")
    return None


async def get_cache_stats(window_days: int = 7) -> dict:
    """Aggregate hit/miss counters over the last `window_days`.

    Returns a dict with `hits`, `misses`, `total`, and `hit_rate` (float|None).
    On Redis error returns zeros — caller reads that as NOT_MEASURED.
    """
    hits = 0
    misses = 0
    try:
        r = await _get_redis()
        today = datetime.now(tz=timezone.utc).date()
        pipe = r.pipeline()
        for offset in range(window_days):
            date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            for prefix in ("llm", "emb"):
                pipe.get(_COUNTER_KEY.format(result="hit", prefix=prefix, date=date))
                pipe.get(_COUNTER_KEY.format(result="miss", prefix=prefix, date=date))
        values = await pipe.execute()
        await r.aclose()
        # Values arrive in pairs (hit, miss) x prefixes x days
        for i in range(0, len(values), 2):
            hits += int(values[i] or 0)
            misses += int(values[i + 1] or 0)
    except Exception:
        return {"hits": 0, "misses": 0, "total": 0, "hit_rate": None}

    total = hits + misses
    return {
        "hits": hits,
        "misses": misses,
        "total": total,
        "hit_rate": (hits / total) if total else None,
    }


async def set_cached_embedding(model: str, text: str, embedding: list[float]) -> None:
    """Store an embedding in cache."""
    try:
        r = await _get_redis()
        key = _cache_key("emb", model, text)
        await r.setex(key, EMBEDDING_CACHE_TTL, json.dumps(embedding))
        await r.aclose()
    except Exception:
        pass
