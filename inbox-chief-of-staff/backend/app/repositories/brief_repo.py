from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.brief import Brief


class BriefRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        user_id: str,
        time_window: str,
        summary_markdown: str,
        action_items: list[str],
        message_ids: list[str],
    ) -> Brief:
        brief = Brief(
            user_id=user_id,
            time_window=time_window,
            summary_markdown=summary_markdown,
            action_items=action_items,
            message_ids=message_ids,
        )
        self.db.add(brief)
        await self.db.commit()
        await self.db.refresh(brief)
        return brief

    async def list_for_user(self, user_id: str, limit: int = 10) -> list[Brief]:
        result = await self.db.execute(
            select(Brief)
            .where(Brief.user_id == user_id)
            .order_by(Brief.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, brief_id: str) -> Brief | None:
        result = await self.db.execute(select(Brief).where(Brief.id == brief_id))
        return result.scalar_one_or_none()
