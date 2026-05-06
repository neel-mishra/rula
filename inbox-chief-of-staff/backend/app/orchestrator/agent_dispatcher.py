from __future__ import annotations
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.policy.action_policy import ActionPolicy, AgentAction
from app.telemetry.events import TelemetryEmitter

logger = structlog.get_logger()
_policy = ActionPolicy()
_telemetry = TelemetryEmitter()


async def dispatch_triage(
    workflow_run_id: str,
    db: AsyncSession,
    fsm,
) -> None:
    """Run TriageAgent, enforce policy, persist TriageResult, advance state."""
    from app.repositories.workflow_repo import WorkflowRepository, TriageRepository
    from app.repositories.message_repo import MessageRepository
    from app.agents.triage_agent import TriageAgent
    from app.ingestion.normalizer import NormalizedMessage
    from app.core.security import decrypt_token
    from app.orchestrator.state_machine import WorkflowState
    from app.models.user import User

    workflow_repo = WorkflowRepository(db)
    triage_repo = TriageRepository(db)
    msg_repo = MessageRepository(db)

    run = await workflow_repo.get_by_id(workflow_run_id)
    if not run:
        logger.error("WorkflowRun not found", workflow_run_id=workflow_run_id)
        return

    # Check policy before proceeding
    _policy.enforce(AgentAction.READ_MESSAGE, "TriageAgent", workflow_run_id)

    # Get message
    from app.models.message import Message
    msg_result = await db.execute(select(Message).where(Message.id == run.message_id))
    message = msg_result.scalar_one_or_none()
    if not message:
        logger.error("Message not found for workflow", workflow_run_id=workflow_run_id)
        return

    # Get user credentials
    user_result = await db.execute(select(User).where(User.id == run.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return

    # Build NormalizedMessage from DB record (avoids re-fetching from Gmail)
    from datetime import timezone
    normalized = NormalizedMessage(
        message_id=message.gmail_message_id,
        thread_id=message.gmail_thread_id,
        subject=message.subject,
        sender_email=message.sender_email,
        sender_name=message.sender_name,
        received_at=message.received_at,
        body_preview=message.body_preview,
        has_attachments=False,
        label_ids=[],
    )

    # Run triage
    agent = TriageAgent(telemetry=_telemetry)
    output = await agent.triage(normalized, workflow_run_id=workflow_run_id, user_id=str(run.user_id))

    # Persist result
    await triage_repo.create(
        workflow_run_id=workflow_run_id,
        priority=output.priority,
        confidence=output.confidence,
        rationale=output.rationale,
        labels=output.labels,
        model_version=agent.model,
    )

    # Advance state
    await fsm.transition(WorkflowState.TRIAGED, db)
    logger.info("Triage complete", workflow_run_id=workflow_run_id, priority=output.priority)

    # Immediately dispatch to next stage
    await fsm.dispatch_agents(db)


async def dispatch_draft(
    workflow_run_id: str,
    db: AsyncSession,
    fsm,
) -> None:
    """Run DraftAgent, create Gmail draft, persist Draft record, advance state."""
    from app.repositories.workflow_repo import WorkflowRepository
    from app.repositories.draft_repo import DraftRepository
    from app.agents.draft_agent import DraftAgent
    from app.ingestion.normalizer import NormalizedMessage
    from app.core.security import decrypt_token
    from app.ingestion.gmail_client import GmailClient
    from app.orchestrator.state_machine import WorkflowState
    from app.models.message import Message
    from app.models.user import User

    workflow_repo = WorkflowRepository(db)
    draft_repo = DraftRepository(db)

    run = await workflow_repo.get_by_id(workflow_run_id)
    if not run:
        return

    # Enforce policy before any action
    _policy.enforce(AgentAction.WRITE_DRAFT, "DraftAgent", workflow_run_id)

    msg_result = await db.execute(select(Message).where(Message.id == run.message_id))
    message = msg_result.scalar_one_or_none()
    if not message:
        return

    user_result = await db.execute(select(User).where(User.id == run.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return

    normalized = NormalizedMessage(
        message_id=message.gmail_message_id,
        thread_id=message.gmail_thread_id,
        subject=message.subject,
        sender_email=message.sender_email,
        sender_name=message.sender_name,
        received_at=message.received_at,
        body_preview=message.body_preview,
        has_attachments=False,
        label_ids=[],
    )

    agent = DraftAgent(telemetry=_telemetry)
    output = await agent.generate_draft(
        message=normalized,
        thread_context=[],
        workflow_run_id=workflow_run_id,
        user_id=str(run.user_id),
    )

    # Create Gmail draft
    refresh_token = decrypt_token(user.google_refresh_token)
    gmail = GmailClient(refresh_token)
    gmail_draft_id = gmail.create_draft(
        to=message.sender_email,
        subject=output.subject_line,
        body=output.draft_body,
    )

    # Persist draft record
    await draft_repo.create(
        workflow_run_id=workflow_run_id,
        body=output.draft_body,
        subject_line=output.subject_line,
        confidence=output.confidence,
        gmail_draft_id=gmail_draft_id,
    )

    await fsm.transition(WorkflowState.PENDING_REVIEW, db)
    logger.info("Draft created", workflow_run_id=workflow_run_id, gmail_draft_id=gmail_draft_id)


async def dispatch_brief(
    workflow_run_id: str,
    db: AsyncSession,
    fsm,
) -> None:
    """Queue message for brief aggregation, advance state to BRIEF_QUEUED."""
    from app.orchestrator.state_machine import WorkflowState
    # In Prototype, brief generation is batch-triggered on schedule, not per-message.
    # Mark this message as brief_queued so the brief scheduler picks it up.
    await fsm.transition(WorkflowState.BRIEF_QUEUED, db)
    logger.info("Message queued for brief", workflow_run_id=workflow_run_id)


async def run_brief_batch(user_id: str, time_window: str, db: AsyncSession) -> None:
    """
    Aggregate all BRIEF_QUEUED messages for a user into a single brief.
    Called by a scheduler (morning/afternoon).
    """
    from app.repositories.workflow_repo import WorkflowRepository
    from app.repositories.brief_repo import BriefRepository
    from app.agents.brief_agent import BriefAgent
    from app.ingestion.normalizer import NormalizedMessage
    from app.models.message import Message, WorkflowRun
    from app.orchestrator.state_machine import WorkflowState, WorkflowStateMachine

    workflow_repo = WorkflowRepository(db)
    brief_repo = BriefRepository(db)

    # Get all brief-queued runs for this user
    pending_runs = await workflow_repo.list_pending_for_user(user_id)
    brief_runs = [r for r in pending_runs if r.state == "brief_queued"]
    if not brief_runs:
        return

    # Fetch messages
    messages = []
    for run in brief_runs:
        msg_result = await db.execute(select(Message).where(Message.id == run.message_id))
        msg = msg_result.scalar_one_or_none()
        if msg:
            messages.append(NormalizedMessage(
                message_id=msg.gmail_message_id,
                thread_id=msg.gmail_thread_id,
                subject=msg.subject,
                sender_email=msg.sender_email,
                sender_name=msg.sender_name,
                received_at=msg.received_at,
                body_preview=msg.body_preview,
                has_attachments=False,
                label_ids=[],
            ))

    # Generate brief
    brief_telemetry = TelemetryEmitter()
    agent = BriefAgent(telemetry=brief_telemetry)
    # Use first run_id as representative for telemetry
    output = await agent.generate_brief(
        messages=messages,
        time_window=time_window,
        workflow_run_id=str(brief_runs[0].id),
        user_id=user_id,
    )

    await brief_repo.create(
        user_id=user_id,
        time_window=time_window,
        summary_markdown=output.summary_markdown,
        action_items=output.action_items,
        message_ids=[str(r.message_id) for r in brief_runs],
    )

    # Advance all brief-queued runs to completed
    for run in brief_runs:
        fsm = WorkflowStateMachine(str(run.id), WorkflowState.BRIEF_QUEUED)
        await fsm.transition(WorkflowState.COMPLETED, db)

    logger.info("Brief generated", user_id=user_id, time_window=time_window, message_count=len(messages))
