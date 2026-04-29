"""
Embedding generation — wraps OpenAI embeddings API (text-embedding-3-small).
Supports batch embedding with automatic chunking.
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog

from core.config import settings

log = structlog.get_logger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_BATCH_SIZE = 100


async def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding vector, with Redis caching."""
    from core.llm.cache import get_cached_embedding, set_cached_embedding

    cached = await get_cached_embedding(EMBEDDING_MODEL, text)
    if cached:
        return cached

    results = await generate_embeddings([text])
    embedding = results[0]

    await set_cached_embedding(EMBEDDING_MODEL, text, embedding)
    return embedding


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts. Chunks large batches automatically."""
    from openai import AsyncOpenAI

    if not texts:
        return []

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[i : i + MAX_BATCH_SIZE]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


def embedding_cache_key(text: str) -> str:
    """Deterministic cache key for an embedding."""
    return f"emb:{EMBEDDING_MODEL}:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
