from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db

logger = structlog.get_logger(__name__)
router = APIRouter()


class RunAgentRequest(BaseModel):
    workflow_run_id: str
    agent_type: str  # triage | draft | brief
    message_id: str


def _verify_worker_auth(x_worker_auth: str | None = Header(default=None)) -> None:
    """Reject requests that don't carry the shared worker secret.

    Cloud Tasks sets this header; anything else (including public traffic that
    somehow reaches this path) is rejected before any work is done.
    """
    if not x_worker_auth or x_worker_auth != settings.worker_auth_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/run-agent", dependencies=[Depends(_verify_worker_auth)])
async def run_agent(
    body: RunAgentRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Internal endpoint called by Cloud Tasks to execute a single agent step.

    Cloud Tasks retries on any 5xx response, so we surface operational errors
    as 500 and permanent/logic errors as 4xx to avoid infinite retry loops.
    """
    from app.repositories.workflow_repo import WorkflowRepository
    from app.orchestrator.state_machine import WorkflowStateMachine, WorkflowState
    from app.orchestrator.agent_dispatcher import dispatch_triage, dispatch_draft, dispatch_brief

    workflow_run_id = body.workflow_run_id
    agent_type = body.agent_type

    if agent_type not in ("triage", "draft", "brief"):
        raise HTTPException(status_code=400, detail=f"Unknown agent_type: {agent_type}")

    repo = WorkflowRepository(db)
    run = await repo.get_by_id(workflow_run_id)
    if not run:
        logger.warning("worker: workflow_run not found", workflow_run_id=workflow_run_id)
        raise HTTPException(status_code=404, detail="WorkflowRun not found")

    fsm = WorkflowStateMachine(workflow_run_id, WorkflowState(run.state.value if hasattr(run.state, "value") else run.state))

    logger.info(
        "worker_dispatching_agent",
        workflow_run_id=workflow_run_id,
        agent_type=agent_type,
        current_state=run.state,
    )

    try:
        if agent_type == "triage":
            await dispatch_triage(workflow_run_id=workflow_run_id, db=db, fsm=fsm)
        elif agent_type == "draft":
            await dispatch_draft(workflow_run_id=workflow_run_id, db=db, fsm=fsm)
        elif agent_type == "brief":
            await dispatch_brief(workflow_run_id=workflow_run_id, db=db, fsm=fsm)
    except Exception as exc:
        logger.error(
            "worker_agent_failed",
            workflow_run_id=workflow_run_id,
            agent_type=agent_type,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok", "workflow_run_id": workflow_run_id, "agent_type": agent_type}
