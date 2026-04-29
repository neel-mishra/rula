"""
Assistant interface — multi-turn conversations that accept natural-language
instructions and compile them into policy rules / memories.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.db import get_db
from core.models.assistant_conversation import AssistantConversation, AssistantMessage
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class InstructionRequest(BaseModel):
    instruction: str
    mailbox_id: uuid.UUID | None = None  # None = user-global
    conversation_id: uuid.UUID | None = None  # None = start a new conversation


class InstructionResponse(BaseModel):
    accepted: bool
    rules_created: int
    feedback_event_id: str
    message: str
    needs_clarification: bool = False
    clarification_question: str | None = None
    conversation_id: str
    user_message_id: str
    assistant_message_id: str


class AssistantMessageOut(BaseModel):
    id: str
    role: str
    content: str
    response_data: dict
    feedback_event_id: str | None
    created_at: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    mailbox_id: str | None
    message_count: int
    last_message_at: str | None
    created_at: str
    updated_at: str
    last_message_preview: str | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
    total: int


class ConversationDetail(BaseModel):
    id: str
    title: str
    mailbox_id: str | None
    message_count: int
    created_at: str
    updated_at: str
    messages: list[AssistantMessageOut]


def _derive_title(instruction: str) -> str:
    stripped = instruction.strip().replace("\n", " ")
    if len(stripped) <= 80:
        return stripped or "New conversation"
    return stripped[:77].rstrip() + "..."


@router.post("/instruction", response_model=InstructionResponse)
async def submit_instruction(
    request: InstructionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InstructionResponse:
    """
    Accept a natural-language instruction. Appends to an existing conversation
    if conversation_id is provided, otherwise creates a new conversation.
    """
    from core.models.feedback import FeedbackEvent
    from core.schemas.contracts import PolicyCompileTask
    from subagents.policy import PolicyAgent

    user_id = user.id
    mailbox_id = request.mailbox_id or uuid.UUID("00000000-0000-0000-0000-000000000000")
    correlation_id = str(uuid.uuid4())

    # Resolve or create conversation
    if request.conversation_id:
        conversation = await db.get(AssistantConversation, request.conversation_id)
        if not conversation or conversation.user_id != user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = AssistantConversation(
            id=uuid.uuid4(),
            user_id=user.id,
            mailbox_id=request.mailbox_id,
            title=_derive_title(request.instruction),
        )
        db.add(conversation)
        await db.flush()

    # FeedbackEvent (pre-existing side effect — policy compilation consumes it)
    feedback = FeedbackEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        mailbox_id=request.mailbox_id,
        feedback_type="assistant_instruction",
        raw_content=request.instruction,
        structured_intent={"conversation_id": str(conversation.id)},
        processed=False,
        correlation_id=correlation_id,
    )
    db.add(feedback)
    await db.flush()

    # Persist user message
    user_message = AssistantMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="user",
        content=request.instruction,
        response_data={},
        feedback_event_id=feedback.id,
    )
    db.add(user_message)

    # Compile policy (synchronous for now)
    agent = PolicyAgent()
    task = PolicyCompileTask(
        user_id=user_id,
        mailbox_id=mailbox_id,
        correlation_id=correlation_id,
        policy_version="v1",
        instruction_text=request.instruction,
        source="assistant",
    )
    response = await agent.run(task)
    payload = response.payload
    rules_created = payload.rules_created if payload else 0
    needs_clarification = bool(payload and payload.needs_clarification)
    clarification_question = payload.clarification_question if payload else None

    if needs_clarification:
        assistant_text = clarification_question or "Could you clarify?"
        accepted = False
    else:
        assistant_text = (
            f"Got it — created {rules_created} rule(s) from your instruction. "
            "This will take effect on the next email processed."
        )
        accepted = True

    response_data = {
        "rules_created": rules_created,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "feedback_event_id": str(feedback.id),
        "accepted": accepted,
    }

    assistant_message = AssistantMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_text,
        response_data=response_data,
        feedback_event_id=feedback.id,
    )
    db.add(assistant_message)

    # Update conversation aggregate fields
    now = datetime.now(tz=timezone.utc)
    conversation.last_message_at = now
    conversation.message_count = (conversation.message_count or 0) + 2
    await db.flush()

    return InstructionResponse(
        accepted=accepted,
        rules_created=rules_created,
        feedback_event_id=str(feedback.id),
        message=assistant_text,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
        conversation_id=str(conversation.id),
        user_message_id=str(user_message.id),
        assistant_message_id=str(assistant_message.id),
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ConversationListResponse:
    base = select(AssistantConversation).where(AssistantConversation.user_id == user.id)
    count_q = select(sa_func.count(AssistantConversation.id)).where(
        AssistantConversation.user_id == user.id
    )
    if mailbox_id:
        base = base.where(AssistantConversation.mailbox_id == mailbox_id)
        count_q = count_q.where(AssistantConversation.mailbox_id == mailbox_id)

    result = await db.execute(
        base.order_by(AssistantConversation.updated_at.desc()).limit(limit).offset(offset)
    )
    conversations = result.scalars().all()
    total = (await db.execute(count_q)).scalar() or 0

    # Preview = most recent message content, truncated
    previews: dict[uuid.UUID, str] = {}
    if conversations:
        conv_ids = [c.id for c in conversations]
        msg_res = await db.execute(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id.in_(conv_ids))
            .order_by(AssistantMessage.created_at.desc())
        )
        for msg in msg_res.scalars().all():
            if msg.conversation_id not in previews:
                preview = msg.content.strip().replace("\n", " ")
                previews[msg.conversation_id] = (
                    preview[:120] + "..." if len(preview) > 120 else preview
                )

    return ConversationListResponse(
        total=total,
        conversations=[
            ConversationSummary(
                id=str(c.id),
                title=c.title,
                mailbox_id=str(c.mailbox_id) if c.mailbox_id else None,
                message_count=c.message_count,
                last_message_at=c.last_message_at.isoformat() if c.last_message_at else None,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
                last_message_preview=previews.get(c.id),
            )
            for c in conversations
        ],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    result = await db.execute(
        select(AssistantConversation)
        .where(AssistantConversation.id == conversation_id)
        .options(selectinload(AssistantConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDetail(
        id=str(conversation.id),
        title=conversation.title,
        mailbox_id=str(conversation.mailbox_id) if conversation.mailbox_id else None,
        message_count=conversation.message_count,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
        messages=[
            AssistantMessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                response_data=m.response_data or {},
                feedback_event_id=str(m.feedback_event_id) if m.feedback_event_id else None,
                created_at=m.created_at.isoformat(),
            )
            for m in sorted(conversation.messages, key=lambda x: x.created_at)
        ],
    )


# ── U.7 — Proactive rule suggestions ─────────────────────────────────────


class AssistantSuggestion(BaseModel):
    id: str                             # stable hash of (kind + signal)
    kind: str                           # "always_inbox" | "stop_brief" | "stop_drafting"
    headline: str                       # one-line summary for the chip
    rationale: str                      # why we're suggesting this
    instruction_text: str               # what to send to /assistant/instruction
    evidence_count: int
    mailbox_id: str | None = None


class AssistantSuggestionsResponse(BaseModel):
    suggestions: list[AssistantSuggestion]
    window_days: int


@router.get("/suggestions", response_model=AssistantSuggestionsResponse)
async def get_suggestions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    window_days: int = Query(30, ge=1, le=180),
    min_evidence: int = Query(2, ge=1, le=20),
) -> AssistantSuggestionsResponse:
    """
    Deterministic rule suggestions derived from recent user corrections +
    undone mutations + discarded drafts. No LLM call — purely heuristic
    over the last `window_days`.
    """
    import hashlib
    from collections import Counter
    from datetime import timedelta as _td

    from core.models.draft import Draft, DraftStatus
    from core.models.email import Email
    from core.models.feedback import FeedbackEvent
    from core.models.triage import TriageDecision, TriageOutcome

    cutoff = datetime.now(tz=timezone.utc) - _td(days=window_days)

    # ── 1. Repeated corrections → "always X for sender Y" ─────────────────
    triage_q = (
        select(TriageDecision, Email.from_address)
        .join(Email, Email.id == TriageDecision.email_id)
        .where(
            TriageDecision.user_id == user.id,
            TriageDecision.corrected_by_user.is_(True),
            TriageDecision.created_at >= cutoff,
        )
    )
    if mailbox_id:
        triage_q = triage_q.where(TriageDecision.mailbox_id == mailbox_id)

    correction_pairs: Counter[tuple[str, str]] = Counter()
    correction_rows = (await db.execute(triage_q)).all()
    for decision, sender in correction_rows:
        if not sender:
            continue
        correction_pairs[(sender, decision.outcome.value)] += 1

    suggestions: list[AssistantSuggestion] = []

    for (sender, outcome), count in correction_pairs.most_common():
        if count < min_evidence:
            break
        # Translate corrected outcome into an actionable user instruction.
        verb_map = {
            TriageOutcome.PROTECTED.value: f"Always keep emails from {sender} in the inbox",
            TriageOutcome.INBOX_KEEP.value: f"Always keep emails from {sender} in the inbox",
            TriageOutcome.BRIEF_ONLY.value: f"Stop putting emails from {sender} in the inbox; brief them instead",
            TriageOutcome.DRAFT_CANDIDATE.value: f"Always draft replies to emails from {sender}",
            TriageOutcome.MANUAL_REVIEW.value: f"Send emails from {sender} to manual review",
        }
        instruction = verb_map.get(outcome, f"Treat emails from {sender} as {outcome}")
        suggestions.append(
            AssistantSuggestion(
                id=hashlib.sha1(f"correction:{sender}:{outcome}".encode()).hexdigest()[:12],
                kind="always_inbox" if outcome in (TriageOutcome.PROTECTED.value, TriageOutcome.INBOX_KEEP.value) else "rebucket",
                headline=f"You corrected {sender} {count}× to {outcome.replace('_', ' ')}",
                rationale=(
                    f"In the last {window_days} days you reclassified {count} email(s) "
                    f"from {sender} to {outcome.replace('_', ' ')}. Codify it as a rule?"
                ),
                instruction_text=instruction,
                evidence_count=count,
                mailbox_id=str(mailbox_id) if mailbox_id else None,
            )
        )

    # ── 2. Repeated discarded drafts for same sender → stop drafting ─────
    discarded_q = (
        select(Email.from_address, sa_func.count(Draft.id))
        .join(Email, Email.id == Draft.email_id)
        .where(
            Draft.user_id == user.id,
            Draft.status == DraftStatus.DISCARDED,
            Draft.created_at >= cutoff,
        )
        .group_by(Email.from_address)
        .having(sa_func.count(Draft.id) >= min_evidence)
    )
    if mailbox_id:
        discarded_q = discarded_q.where(Draft.mailbox_id == mailbox_id)

    for sender, count in (await db.execute(discarded_q)).all():
        if not sender:
            continue
        suggestions.append(AssistantSuggestion(
            id=hashlib.sha1(f"discard:{sender}".encode()).hexdigest()[:12],
            kind="stop_drafting",
            headline=f"You discarded {count} drafts to {sender}",
            rationale=(
                f"Over the last {window_days} days, every generated draft for {sender} "
                "was discarded. Want the assistant to stop drafting for them?"
            ),
            instruction_text=f"Never draft replies to emails from {sender}",
            evidence_count=count,
            mailbox_id=str(mailbox_id) if mailbox_id else None,
        ))

    # Cap the list — chat UI shouldn't drown the user.
    return AssistantSuggestionsResponse(
        suggestions=suggestions[:6],
        window_days=window_days,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await db.get(AssistantConversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conversation)
    return {"deleted": True, "conversation_id": str(conversation_id)}
