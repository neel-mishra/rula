from __future__ import annotations
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.message import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_gmail_id(self, gmail_message_id: str, user_id: str) -> Message | None:
        result = await self.db.execute(
            select(Message).where(
                and_(Message.gmail_message_id == gmail_message_id, Message.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: str,
        gmail_message_id: str,
        gmail_thread_id: str,
        subject: str,
        sender_email: str,
        sender_name: str,
        received_at: datetime,
        body_preview: str,
        ingest_status: str = "pending",
    ) -> Message:
        msg = Message(
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            gmail_thread_id=gmail_thread_id,
            subject=subject,
            sender_email=sender_email,
            sender_name=sender_name,
            received_at=received_at,
            body_preview=body_preview[:500],
            ingest_status=ingest_status,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def update_status(self, message: Message, status: str) -> Message:
        message.ingest_status = status
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
