from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.message import WorkflowRun, TriageResult


class WorkflowRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, workflow_run_id: str) -> WorkflowRun | None:
        result = await self.db.execute(
            select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
        )
        return result.scalar_one_or_none()

    async def get_by_message_id(self, message_id: str) -> WorkflowRun | None:
        result = await self.db.execute(
            select(WorkflowRun).where(WorkflowRun.message_id == message_id)
        )
        return result.scalar_one_or_none()

    async def update_state(self, run: WorkflowRun, new_state: str) -> WorkflowRun:
        run.state = new_state
        if new_state in ("completed", "rejected"):
            run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_pending_for_user(self, user_id: str, limit: int = 50) -> list[WorkflowRun]:
        result = await self.db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.user_id == user_id)
            .where(WorkflowRun.state.in_(["ingested", "normalized", "triaged", "draft_queued", "brief_queued", "pending_review"]))
            .order_by(WorkflowRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class TriageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        workflow_run_id: str,
        priority: str,
        confidence: float,
        rationale: str,
        labels: list[str],
        model_version: str,
    ) -> TriageResult:
        result = TriageResult(
            workflow_run_id=workflow_run_id,
            priority=priority,
            confidence=confidence,
            rationale=rationale,
            labels=labels,
            model_version=model_version,
        )
        self.db.add(result)
        await self.db.commit()
        await self.db.refresh(result)
        return result

    async def get_by_workflow_run(self, workflow_run_id: str) -> TriageResult | None:
        result = await self.db.execute(
            select(TriageResult).where(TriageResult.workflow_run_id == workflow_run_id)
        )
        return result.scalar_one_or_none()
