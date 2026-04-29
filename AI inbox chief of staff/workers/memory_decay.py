"""
Memory confidence decay — reduces confidence over time and deactivates expired memories.
Runs daily via scheduler.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update

from core.db import get_db_session
from core.models.memory import Memory

log = structlog.get_logger(__name__)

# Decay 5% per week for memories not reinforced in the last 14 days
DECAY_RATE = 0.05
DECAY_GRACE_PERIOD_DAYS = 14
DEACTIVATION_THRESHOLD = 0.3


async def run_memory_decay() -> dict:
    """Decay confidence on stale memories and deactivate expired ones."""
    results = {"decayed": 0, "deactivated": 0, "expired": 0}
    now = datetime.now(tz=timezone.utc)
    grace_cutoff = now - timedelta(days=DECAY_GRACE_PERIOD_DAYS)

    async with get_db_session() as session:
        # Deactivate memories past their expiry date
        expire_result = await session.execute(
            update(Memory)
            .where(
                Memory.is_active == True,  # noqa: E712
                Memory.expires_at.isnot(None),
                Memory.expires_at <= now,
            )
            .values(is_active=False)
        )
        results["expired"] = expire_result.rowcount

        # Decay confidence on memories not reinforced recently
        stale_result = await session.execute(
            select(Memory).where(
                Memory.is_active == True,  # noqa: E712
                Memory.confidence > DEACTIVATION_THRESHOLD,
                (
                    (Memory.last_reinforced_at.is_(None))
                    | (Memory.last_reinforced_at < grace_cutoff)
                ),
            )
        )
        stale_memories = stale_result.scalars().all()

        for memory in stale_memories:
            new_confidence = max(0.0, memory.confidence - DECAY_RATE)

            if new_confidence <= DEACTIVATION_THRESHOLD:
                memory.is_active = False
                memory.confidence = new_confidence
                results["deactivated"] += 1
                log.info(
                    "memory_decay.deactivated",
                    memory_id=str(memory.id),
                    old_confidence=memory.confidence,
                )
            else:
                memory.confidence = new_confidence
                results["decayed"] += 1

    log.info("memory_decay.complete", **results)
    return results
