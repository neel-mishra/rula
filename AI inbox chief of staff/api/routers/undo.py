"""
Undo endpoint — reverse any system-initiated mailbox mutation by undo token.
Guarantees reversibility within the configured policy window (default 7 days).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from core.db import get_db
from core.models.email import Email
from core.models.mutation_ledger import MutationLedger, MutationStatus
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class UndoRequest(BaseModel):
    undo_token: str


class UndoResponse(BaseModel):
    ledger_id: str
    reversed: bool
    message: str


class MutationSummary(BaseModel):
    id: str
    mailbox_id: str
    mutation_type: str
    status: str
    email_subject: str | None
    email_from: str | None
    reason_trace: str
    undo_token: str
    undo_expires_at: str
    created_at: str


class MutationListResponse(BaseModel):
    mutations: list[MutationSummary]
    total: int


@router.get("/mutations", response_model=MutationListResponse)
async def list_mutations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None, description="pending | applied | undone | expired"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> MutationListResponse:
    """Recent system-initiated mutations for this user, newest first."""
    from sqlalchemy import func as sa_func

    base = select(MutationLedger).where(MutationLedger.user_id == user.id)
    count_q = select(sa_func.count(MutationLedger.id)).where(MutationLedger.user_id == user.id)

    if mailbox_id:
        base = base.where(MutationLedger.mailbox_id == mailbox_id)
        count_q = count_q.where(MutationLedger.mailbox_id == mailbox_id)
    if status:
        try:
            status_enum = MutationStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        base = base.where(MutationLedger.status == status_enum)
        count_q = count_q.where(MutationLedger.status == status_enum)

    result = await db.execute(
        base.order_by(MutationLedger.created_at.desc()).limit(limit).offset(offset)
    )
    ledgers = result.scalars().all()

    # Batch-fetch emails for subject/from columns
    email_ids = [ledger.email_id for ledger in ledgers]
    email_map: dict[uuid.UUID, Email] = {}
    if email_ids:
        emails = await db.execute(select(Email).where(Email.id.in_(email_ids)))
        for email in emails.scalars().all():
            email_map[email.id] = email

    total = (await db.execute(count_q)).scalar() or 0

    return MutationListResponse(
        total=total,
        mutations=[
            MutationSummary(
                id=str(ledger.id),
                mailbox_id=str(ledger.mailbox_id),
                mutation_type=ledger.mutation_type.value,
                status=ledger.status.value,
                email_subject=(email_map.get(ledger.email_id).subject if email_map.get(ledger.email_id) else None),
                email_from=(email_map.get(ledger.email_id).from_address if email_map.get(ledger.email_id) else None),
                reason_trace=ledger.reason_trace,
                undo_token=ledger.undo_token,
                undo_expires_at=ledger.undo_expires_at.isoformat(),
                created_at=ledger.created_at.isoformat(),
            )
            for ledger in ledgers
        ],
    )


@router.post("/mutation", response_model=UndoResponse)
async def undo_mutation(
    request: UndoRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UndoResponse:
    """
    Undo a system-initiated archive/label action by undo token.
    Must be within undo window. Idempotent.
    """
    result = await db.execute(
        select(MutationLedger).where(MutationLedger.undo_token == request.undo_token)
    )
    ledger = result.scalar_one_or_none()

    if not ledger:
        raise HTTPException(status_code=404, detail="Undo token not found")

    if ledger.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your mutation")

    if ledger.status == MutationStatus.UNDONE:
        return UndoResponse(
            ledger_id=str(ledger.id),
            reversed=True,
            message="Already undone",
        )

    if ledger.status == MutationStatus.EXPIRED:
        raise HTTPException(status_code=410, detail="Undo window expired")

    now = datetime.now(tz=timezone.utc)
    if now > ledger.undo_expires_at:
        ledger.status = MutationStatus.EXPIRED
        raise HTTPException(status_code=410, detail="Undo window expired")

    if ledger.status != MutationStatus.APPLIED:
        raise HTTPException(status_code=409, detail=f"Cannot undo: mutation status is {ledger.status}")

    # Execute Gmail revert
    try:
        from core.db import get_db_session
        from core.models.email import Email
        from core.models.mailbox import Mailbox
        from core.gmail import GmailClient

        email = await db.get(Email, ledger.email_id)
        mailbox = await db.get(Mailbox, ledger.mailbox_id)

        if email and mailbox:
            gmail = GmailClient(mailbox)
            prior_labels = ledger.prior_state.get("labels", [])
            new_labels = ledger.new_state.get("labels", [])

            # Remove labels that were added
            labels_to_remove = [l for l in new_labels if l not in prior_labels]
            # Add back labels that were removed
            labels_to_restore = [l for l in prior_labels if l not in new_labels]

            gmail.modify_message_labels(
                message_id=email.gmail_message_id,
                add_label_ids=labels_to_restore if labels_to_restore else None,
                remove_label_ids=labels_to_remove if labels_to_remove else None,
            )

        ledger.status = MutationStatus.UNDONE
        ledger.undone_at = now

        # Write audit event
        from core.models.audit import AuditEvent
        audit = AuditEvent(
            id=uuid.uuid4(),
            user_id=ledger.user_id,
            mailbox_id=ledger.mailbox_id,
            event_type="mutation.undo",
            actor="user",
            resource_type="email",
            resource_id=str(ledger.email_id),
            payload={
                "ledger_id": str(ledger.id),
                "prior_state": ledger.prior_state,
                "undo_token_prefix": request.undo_token[:8],
            },
            severity="info",
            correlation_id=str(uuid.uuid4()),
        )
        db.add(audit)

        return UndoResponse(
            ledger_id=str(ledger.id),
            reversed=True,
            message="Mutation successfully reversed",
        )

    except Exception as exc:
        ledger.status = MutationStatus.UNDO_FAILED
        raise HTTPException(status_code=500, detail=f"Undo failed: {exc}")
