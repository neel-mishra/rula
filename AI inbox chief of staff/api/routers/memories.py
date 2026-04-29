"""Memory management endpoints — list, edit, deactivate, delete learned memories."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.models.memory import Memory, MemoryScope, MemoryType
from core.models.user import User
from core.security.auth import get_current_user

router = APIRouter()


class MemoryOut(BaseModel):
    id: str
    user_id: str
    mailbox_id: str | None
    scope: str
    applies_to_all_mailboxes: bool
    memory_type: str
    content: str
    structured_data: dict
    source: str
    confidence: float
    is_active: bool
    last_reinforced_at: str | None
    expires_at: str | None
    created_at: str
    updated_at: str


class MemoryListResponse(BaseModel):
    memories: list[MemoryOut]
    total: int


class MemoryUpdate(BaseModel):
    content: str | None = None
    is_active: bool | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class MemoryCreate(BaseModel):
    mailbox_id: uuid.UUID | None = None
    scope: str = "mailbox_specific"     # mailbox_specific | user_global
    memory_type: str                    # profile | policy | style | sender
    content: str
    structured_data: dict = Field(default_factory=dict)
    source: str = "manual"
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    applies_to_all_mailboxes: bool = False


def _to_out(m: Memory) -> MemoryOut:
    return MemoryOut(
        id=str(m.id),
        user_id=str(m.user_id),
        mailbox_id=str(m.mailbox_id) if m.mailbox_id else None,
        scope=m.scope.value,
        applies_to_all_mailboxes=m.applies_to_all_mailboxes,
        memory_type=m.memory_type.value,
        content=m.content,
        structured_data=m.structured_data or {},
        source=m.source,
        confidence=m.confidence,
        is_active=m.is_active,
        last_reinforced_at=m.last_reinforced_at.isoformat() if m.last_reinforced_at else None,
        expires_at=m.expires_at.isoformat() if m.expires_at else None,
        created_at=m.created_at.isoformat(),
        updated_at=m.updated_at.isoformat(),
    )


@router.get("/", response_model=MemoryListResponse)
async def list_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mailbox_id: uuid.UUID | None = Query(None),
    scope: str | None = Query(None, description="mailbox_specific | user_global"),
    memory_type: str | None = Query(None, description="profile | policy | style | sender"),
    is_active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MemoryListResponse:
    base = select(Memory).where(Memory.user_id == user.id)
    count_q = select(sa_func.count(Memory.id)).where(Memory.user_id == user.id)

    if mailbox_id:
        base = base.where(Memory.mailbox_id == mailbox_id)
        count_q = count_q.where(Memory.mailbox_id == mailbox_id)
    if scope:
        try:
            scope_enum = MemoryScope(scope)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}")
        base = base.where(Memory.scope == scope_enum)
        count_q = count_q.where(Memory.scope == scope_enum)
    if memory_type:
        try:
            type_enum = MemoryType(memory_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid memory_type: {memory_type}")
        base = base.where(Memory.memory_type == type_enum)
        count_q = count_q.where(Memory.memory_type == type_enum)
    if is_active is not None:
        base = base.where(Memory.is_active == is_active)
        count_q = count_q.where(Memory.is_active == is_active)

    result = await db.execute(
        base.order_by(Memory.updated_at.desc()).limit(limit).offset(offset)
    )
    memories = result.scalars().all()
    total = (await db.execute(count_q)).scalar() or 0

    return MemoryListResponse(
        total=total,
        memories=[_to_out(m) for m in memories],
    )


@router.post("/", response_model=MemoryOut)
async def create_memory(
    req: MemoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryOut:
    try:
        scope_enum = MemoryScope(req.scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {req.scope}")
    try:
        type_enum = MemoryType(req.memory_type)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid memory_type: {req.memory_type}"
        )

    # Validate mailbox ownership if scoped
    if scope_enum == MemoryScope.MAILBOX_SPECIFIC:
        if not req.mailbox_id:
            raise HTTPException(
                status_code=400,
                detail="mailbox_id required for mailbox_specific scope",
            )
        from core.models.mailbox import Mailbox
        mailbox = await db.get(Mailbox, req.mailbox_id)
        if not mailbox or mailbox.user_id != user.id:
            raise HTTPException(status_code=404, detail="Mailbox not found")

    memory = Memory(
        id=uuid.uuid4(),
        user_id=user.id,
        mailbox_id=req.mailbox_id if scope_enum == MemoryScope.MAILBOX_SPECIFIC else None,
        scope=scope_enum,
        applies_to_all_mailboxes=req.applies_to_all_mailboxes,
        memory_type=type_enum,
        content=req.content,
        structured_data=req.structured_data,
        source=req.source,
        confidence=req.confidence,
        is_active=True,
    )
    db.add(memory)
    await db.flush()
    return _to_out(memory)


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryOut:
    memory = await db.get(Memory, memory_id)
    if not memory or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _to_out(memory)


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: uuid.UUID,
    update: MemoryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryOut:
    memory = await db.get(Memory, memory_id)
    if not memory or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")

    if update.content is not None:
        memory.content = update.content
    if update.is_active is not None:
        memory.is_active = update.is_active
    if update.confidence is not None:
        memory.confidence = update.confidence

    await db.flush()
    return _to_out(memory)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    memory = await db.get(Memory, memory_id)
    if not memory or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(memory)
    return {"deleted": True, "memory_id": str(memory_id)}
