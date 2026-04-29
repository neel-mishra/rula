"""
Sender reputation scoring — per-mailbox sender/domain frequency and response tracking.
Scores are computed from historical email patterns, not external services.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import func, select

log = structlog.get_logger(__name__)


@dataclass
class SenderReputation:
    sender_address: str
    sender_domain: str
    total_received: int
    total_replied_to: int
    reply_rate: float
    is_vip: bool
    is_frequent: bool
    score: float  # 0.0 (spam-like) to 1.0 (VIP)


async def compute_sender_reputation(
    mailbox_id: uuid.UUID,
    sender_address: str,
    sender_domain: str,
    session: Any,
) -> SenderReputation:
    """
    Compute sender reputation from historical patterns in this mailbox.
    Factors: frequency, reply rate, direct-to-user ratio.
    """
    from core.models.email import Email

    # Count total emails from this sender in this mailbox
    total_result = await session.execute(
        select(func.count()).where(
            Email.mailbox_id == mailbox_id,
            Email.from_address == sender_address,
        )
    )
    total_received = total_result.scalar() or 0

    # Count emails from this sender in threads where mailbox user replied
    replied_result = await session.execute(
        select(func.count(func.distinct(Email.gmail_thread_id))).where(
            Email.mailbox_id == mailbox_id,
            Email.from_address == sender_address,
            Email.gmail_thread_id.in_(
                select(Email.gmail_thread_id).where(
                    Email.mailbox_id == mailbox_id,
                    Email.features["is_sent"].as_boolean() == True,  # noqa: E712
                )
            ),
        )
    )
    total_replied_to = replied_result.scalar() or 0

    # Count total emails from this domain
    domain_total_result = await session.execute(
        select(func.count()).where(
            Email.mailbox_id == mailbox_id,
            Email.from_domain == sender_domain,
        )
    )
    domain_total = domain_total_result.scalar() or 0

    reply_rate = total_replied_to / total_received if total_received > 0 else 0.0

    # Heuristic scoring
    score = 0.5  # baseline
    if reply_rate > 0.3:
        score += 0.2
    if reply_rate > 0.6:
        score += 0.1
    if total_received >= 10:
        score += 0.1  # established sender
    if total_received >= 50:
        score += 0.05
    if total_received == 1:
        score -= 0.1  # first-time sender

    score = max(0.0, min(1.0, score))

    is_vip = score >= 0.75 and reply_rate > 0.3 and total_received >= 3
    is_frequent = total_received >= 5

    return SenderReputation(
        sender_address=sender_address,
        sender_domain=sender_domain,
        total_received=total_received,
        total_replied_to=total_replied_to,
        reply_rate=reply_rate,
        is_vip=is_vip,
        is_frequent=is_frequent,
        score=score,
    )
