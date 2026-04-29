"""
Database connection management.
Async SQLAlchemy engine + session factory.
pgvector extension bootstrapped on first connect.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

log = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def _build_engine() -> AsyncEngine:
    engine_kwargs: dict = {
        "echo": settings.app_env == "dev",
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_pre_ping": True,
    }
    # SQLite (tests) doesn't support pooling kwargs
    if "sqlite" in settings.database_url:
        engine_kwargs.pop("pool_size", None)
        engine_kwargs.pop("max_overflow", None)

    return create_async_engine(settings.database_url, **engine_kwargs)


engine: AsyncEngine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context-manager session for background workers."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session and commits/rolls back automatically."""
    async with get_db_session() as session:
        yield session


async def init_db() -> None:
    """
    Bootstrap DB on startup:
    - Enable pgvector extension.
    - Create all tables (only used in dev/test; prod uses Alembic migrations).
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Enable pgvector (idempotent)
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            log.info("pgvector extension enabled")
        except Exception as exc:
            log.warning("pgvector extension not available", error=str(exc))

        if settings.app_env in ("dev", "test"):
            # Import models so Base.metadata is populated
            import core.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)
            log.info("dev/test tables created")


async def dispose_db() -> None:
    """Dispose engine on shutdown."""
    await engine.dispose()
    log.info("database engine disposed")
