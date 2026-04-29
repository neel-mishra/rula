"""
Test configuration and fixtures.

Supports two backends:
  - SQLite in-memory (default, for fast local runs)
  - PostgreSQL (when DATABASE_URL points to a real Postgres, e.g. in CI)

SQLite mode patches JSONB/ARRAY DDL compilation so models work unchanged.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Force test environment
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("APP_SECRET_KEY", "test_secret_key_minimum_32_characters_here")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("OPENAI_API_KEY", "test_key")

# ── Detect backend ────────────────────────────────────────────────────────────
_db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
_is_sqlite = "sqlite" in _db_url.lower()

# ── Patch SQLite DDL compiler for Postgres-specific types ─────────────────────
# Teaches SQLite how to render JSONB → JSON and ARRAY(X) → JSON in CREATE TABLE
# without modifying any model code.
if _is_sqlite:
    import json

    from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(type_, compiler, **kw):
        return "JSON"

    @compiles(ARRAY, "sqlite")
    def _compile_array_sqlite(type_, compiler, **kw):
        return "JSON"

    @compiles(PG_UUID, "sqlite")
    def _compile_uuid_sqlite(type_, compiler, **kw):
        return "VARCHAR(32)"

    # Teach ARRAY how to bind/return values in SQLite (JSON serialization)
    _original_array_bind = ARRAY.bind_processor

    def _patched_array_bind(self, dialect):
        if dialect.name == "sqlite":
            def process(value):
                if value is None:
                    return None
                return json.dumps(value)
            return process
        if _original_array_bind:
            return _original_array_bind(self, dialect)
        return None

    ARRAY.bind_processor = _patched_array_bind

    _original_array_result = ARRAY.result_processor

    def _patched_array_result(self, dialect, coltype):
        if dialect.name == "sqlite":
            def process(value):
                if value is None:
                    return None
                if isinstance(value, str):
                    return json.loads(value)
                return value
            return process
        if _original_array_result:
            return _original_array_result(self, dialect, coltype)
        return None

    ARRAY.result_processor = _patched_array_result

    # Teach PG UUID how to bind/return values in SQLite (store as hex string)
    _original_uuid_bind = PG_UUID.bind_processor

    def _patched_uuid_bind(self, dialect):
        if dialect.name == "sqlite":
            def process(value):
                if value is None:
                    return None
                if isinstance(value, uuid.UUID):
                    return value.hex
                return str(value).replace("-", "")
            return process
        if _original_uuid_bind:
            return _original_uuid_bind(self, dialect)
        return None

    PG_UUID.bind_processor = _patched_uuid_bind

    _original_uuid_result = PG_UUID.result_processor

    def _patched_uuid_result(self, dialect, coltype):
        if dialect.name == "sqlite":
            def process(value):
                if value is None:
                    return None
                if isinstance(value, uuid.UUID):
                    return value
                if isinstance(value, int):
                    return uuid.UUID(int=value)
                if isinstance(value, bytes):
                    return uuid.UUID(bytes=value)
                return uuid.UUID(str(value))
            return process
        if _original_uuid_result:
            return _original_uuid_result(self, dialect, coltype)
        return None

    PG_UUID.result_processor = _patched_uuid_result


from core.db import Base, get_db
from api.main import app

# Import all models so Base.metadata is populated
import core.models  # noqa: F401


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(_db_url, echo=False)

    if _is_sqlite:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    else:
        # On Postgres: run Alembic migrations so triggers, extensions, and enum
        # alterations (e.g. delivery_failed) are applied.
        import subprocess, sys
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={**os.environ, "DATABASE_URL": _db_url.replace("+asyncpg", "")},
        )
        if result.returncode != 0:
            # Alembic may fail if tables exist; fall back to create_all
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(db_session):
    """Client with a valid session JWT for a test user."""
    from core.models.user import User
    from core.security.auth import create_session_token

    async def override_get_db():
        yield db_session

    # Create test user
    user = User(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="test@example.com",
        display_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    token = create_session_token(user_id=user.id, email=user.email)

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_mailbox_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def sample_correlation_id() -> str:
    return str(uuid.uuid4())
