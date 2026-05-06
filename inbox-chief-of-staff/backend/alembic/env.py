import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import os

# Import all models so Alembic can autogenerate migrations
from app.models.base import Base  # noqa: F401
from app.models.user import User, MailboxConnection  # noqa: F401
from app.models.message import Message, WorkflowRun, TriageResult  # noqa: F401
from app.models.draft import Draft  # noqa: F401
from app.models.brief import Brief  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401

config = context.config

# Load .env so `make migrate` works without manually exporting DATABASE_URL.
# pydantic-settings already depends on python-dotenv, so it's always available.
from dotenv import load_dotenv  # noqa: E402
load_dotenv()

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/inbox_chief"),
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
