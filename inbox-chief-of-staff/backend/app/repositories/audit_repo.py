from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        user_id: str,
        event_type: str,
        action: str,
        outcome: str,
        agent_name: str | None = None,
        workflow_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            user_id=user_id,
            event_type=event_type,
            action=action,
            outcome=outcome,
            agent_name=agent_name,
            workflow_run_id=workflow_run_id,
            metadata_=metadata or {},
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[AuditEvent]:
        q = select(AuditEvent).where(AuditEvent.user_id == user_id)
        if since:
            q = q.where(AuditEvent.created_at >= since)
        q = q.order_by(AuditEvent.created_at.desc()).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())
