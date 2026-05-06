from __future__ import annotations
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, MailboxConnection


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, email: str, encrypted_refresh_token: str, timezone: str = "UTC") -> User:
        user = User(email=email, google_refresh_token=encrypted_refresh_token, timezone=timezone)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_refresh_token(self, user: User, encrypted_refresh_token: str) -> User:
        user.google_refresh_token = encrypted_refresh_token
        await self.db.commit()
        await self.db.refresh(user)
        return user


class MailboxRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user(self, user_id: str) -> MailboxConnection | None:
        result = await self.db.execute(
            select(MailboxConnection).where(MailboxConnection.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: str, gmail_address: str) -> MailboxConnection:
        existing = await self.get_by_user(user_id)
        if existing:
            existing.gmail_address = gmail_address
            existing.status = "active"
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        conn = MailboxConnection(user_id=user_id, gmail_address=gmail_address, status="active")
        self.db.add(conn)
        await self.db.commit()
        await self.db.refresh(conn)
        return conn

    async def update_watch_expiry(self, mailbox: MailboxConnection, expiry: datetime) -> None:
        mailbox.watch_expiry = expiry
        await self.db.commit()
