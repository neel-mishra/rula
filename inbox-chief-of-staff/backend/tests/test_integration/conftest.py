"""Integration test fixtures.

DATABASE_URL must be set BEFORE any app imports. We set it here and also
override it in the environment so that app.core.config.settings picks up the
test database when this module is first imported.
"""
from __future__ import annotations

import os

# Override DATABASE_URL to point at the integration-test database BEFORE
# any app module is imported (settings is a module-level singleton).
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://postgres:postgres@localhost:5433/inbox_chief_test"
)
# Dummy creds already expected by conftest.py at the project root:
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("LLM_API_KEY", "test-llm-api-key")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-32-chars-long!")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.security import encrypt_token

TEST_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5433/inbox_chief_test"
)

# Separate engine bound to the test database.  NullPool avoids connection
# reuse issues between test runs.
from sqlalchemy.pool import NullPool

test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, future=True)


@pytest_asyncio.fixture
async def async_session():
    """
    Yield an AsyncSession backed by a real Postgres transaction that is always
    rolled back at the end of the test, giving full isolation without
    truncating tables between runs.

    The inner code under test calls ``await session.commit()``.  Those commits
    flush to the outer connection-level transaction (they don't permanently
    persist because the outer transaction is never committed — it is rolled
    back in the finally block).
    """
    async with test_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession):
    """
    Insert a User + MailboxConnection into the test DB and return the User.

    The google_refresh_token is stored encrypted (matching what
    decrypt_token() in the handlers expects).
    """
    from app.models.user import User, MailboxConnection

    encrypted = encrypt_token("fake-refresh-token")
    user = User(
        email="integration-test@example.com",
        google_refresh_token=encrypted,
        timezone="UTC",
    )
    async_session.add(user)
    await async_session.flush()          # gets the server-generated UUID
    await async_session.refresh(user)

    mailbox = MailboxConnection(
        user_id=user.id,
        gmail_address="integration-test@example.com",
        status="active",
    )
    async_session.add(mailbox)
    await async_session.flush()

    return user
