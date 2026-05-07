from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class WorkflowState(str, Enum):
    INGESTED = "ingested"
    NORMALIZED = "normalized"
    TRIAGED = "triaged"
    DRAFT_QUEUED = "draft_queued"
    BRIEF_QUEUED = "brief_queued"
    FOLLOW_UP_FLAGGED = "follow_up_flagged"
    PENDING_REVIEW = "pending_review"
    COMPLETED = "completed"
    REJECTED = "rejected"


VALID_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.INGESTED: {WorkflowState.NORMALIZED, WorkflowState.REJECTED},
    WorkflowState.NORMALIZED: {WorkflowState.TRIAGED, WorkflowState.REJECTED},
    WorkflowState.TRIAGED: {
        WorkflowState.DRAFT_QUEUED,
        WorkflowState.BRIEF_QUEUED,
        WorkflowState.FOLLOW_UP_FLAGGED,
        WorkflowState.COMPLETED,
    },
    WorkflowState.DRAFT_QUEUED: {WorkflowState.PENDING_REVIEW, WorkflowState.REJECTED},
    WorkflowState.BRIEF_QUEUED: {WorkflowState.PENDING_REVIEW, WorkflowState.COMPLETED},
    WorkflowState.FOLLOW_UP_FLAGGED: {WorkflowState.PENDING_REVIEW, WorkflowState.COMPLETED},
    WorkflowState.PENDING_REVIEW: {WorkflowState.COMPLETED, WorkflowState.REJECTED},
    WorkflowState.COMPLETED: set(),
    WorkflowState.REJECTED: set(),
}


class InvalidTransitionError(Exception):
    pass


class WorkflowStateMachine:
    def __init__(self, workflow_run_id: str, current_state: WorkflowState) -> None:
        self.workflow_run_id = workflow_run_id
        self.current_state = current_state

    async def transition(self, new_state: WorkflowState, db: AsyncSession) -> None:
        """Validate, persist new state, emit structured log."""
        if new_state not in VALID_TRANSITIONS.get(self.current_state, set()):
            raise InvalidTransitionError(
                f"Cannot transition {self.current_state} → {new_state} in {self.workflow_run_id}"
            )
        from app.repositories.workflow_repo import WorkflowRepository
        repo = WorkflowRepository(db)
        run = await repo.get_by_id(self.workflow_run_id)
        if not run:
            raise ValueError(f"WorkflowRun {self.workflow_run_id} not found")
        await repo.update_state(run, new_state.value)
        logger.info(
            "workflow_state_transition",
            workflow_run_id=self.workflow_run_id,
            from_state=self.current_state.value,
            to_state=new_state.value,
        )
        self.current_state = new_state

    async def dispatch_agents(self, db: AsyncSession) -> None:
        """Route to correct agent based on current state."""
        from app.orchestrator.agent_dispatcher import maybe_enqueue
        from app.repositories.workflow_repo import WorkflowRepository

        repo = WorkflowRepository(db)
        run = await repo.get_by_id(self.workflow_run_id)
        message_id = str(run.message_id) if run else ""

        if self.current_state == WorkflowState.NORMALIZED:
            await maybe_enqueue(
                workflow_run_id=self.workflow_run_id,
                agent_type="triage",
                message_id=message_id,
                db=db,
                fsm=self,
            )

        elif self.current_state == WorkflowState.TRIAGED:
            from app.repositories.workflow_repo import TriageRepository
            triage_repo = TriageRepository(db)
            triage = await triage_repo.get_by_workflow_run(self.workflow_run_id)
            if triage and triage.priority in ("urgent", "normal"):
                await self.transition(WorkflowState.DRAFT_QUEUED, db)
                await maybe_enqueue(
                    workflow_run_id=self.workflow_run_id,
                    agent_type="draft",
                    message_id=message_id,
                    db=db,
                    fsm=self,
                )
            else:
                await maybe_enqueue(
                    workflow_run_id=self.workflow_run_id,
                    agent_type="brief",
                    message_id=message_id,
                    db=db,
                    fsm=self,
                )
        else:
            logger.warning("dispatch_agents called in unexpected state", state=self.current_state)
