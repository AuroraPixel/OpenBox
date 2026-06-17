"""Alembic migration environment — async PostgreSQL support."""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from db.base import Base

# Import all models so Alembic can detect them
import db.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Allow DATABASE_URL env var to override alembic.ini
database_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def render_item(type_, obj, autogen_context):
    """Render JSONType as JSONB with SQLite fallback in migration scripts."""
    if type_ == "type" and isinstance(obj, JSONType):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return 'postgresql.JSONB().with_variant(sa.Text(), "sqlite")'
    return False


from db.base import JSONType  # noqa: E402


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, render_item=render_item)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(database_url, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
