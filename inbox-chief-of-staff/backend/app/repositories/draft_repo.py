from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.draft import Draft


class DraftRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        workflow_run_id: str,
        body: str,
        subject_line: str,
        confidence: float,
        gmail_draft_id: str | None = None,
    ) -> Draft:
        draft = Draft(
            workflow_run_id=workflow_run_id,
            body=body,
            subject_line=subject_line,
            confidence=confidence,
            gmail_draft_id=gmail_draft_id,
            status="pending",
        )
        self.db.add(draft)
        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def get_by_id(self, draft_id: str) -> Draft | None:
        result = await self.db.execute(select(Draft).where(Draft.id == draft_id))
        return result.scalar_one_or_none()

    async def get_pending_for_user(self, user_id: str) -> list[Draft]:
        """Fetch all pending drafts for a user via workflow_run join."""
        from app.models.message import WorkflowRun
        result = await self.db.execute(
            select(Draft)
            .join(WorkflowRun, Draft.workflow_run_id == WorkflowRun.id)
            .where(WorkflowRun.user_id == user_id)
            .where(Draft.status == "pending")
            .order_by(Draft.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, draft: Draft, **kwargs) -> Draft:
        for k, v in kwargs.items():
            setattr(draft, k, v)
        await self.db.commit()
        await self.db.refresh(draft)
        return draft
