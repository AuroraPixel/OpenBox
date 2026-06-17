"""SQLAlchemy async engine, session factory, and base model."""
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

import sqlalchemy as sa
from sqlalchemy import TypeDecorator, Text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass

from core.log import create_logger

log = create_logger("db")

# ---------------------------------------------------------------------------
# Cross-database JSONB type
# ---------------------------------------------------------------------------

class JSONType(TypeDecorator):
    """JSONB on PostgreSQL, JSON-as-TEXT on SQLite / others."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is not None and dialect.name != "postgresql":
            return json.dumps(value, ensure_ascii=False)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and isinstance(value, str):
            return json.loads(value)
        return value


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    type_annotation_map = {
        dict: JSONType,
        datetime: sa.DateTime(timezone=True),
    }


# ---------------------------------------------------------------------------
# Engine & session factory (module-level singletons, lazily initialized)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str, pool_size: int = 10, pool_overflow: int = 20) -> AsyncEngine:
    """Create and store the async engine singleton."""
    global _engine, _session_factory

    connect_args = {}
    # SQLite doesn't support pool_size / pool_overflow
    if "sqlite" in database_url:
        _engine = create_async_engine(database_url, echo=False)
    else:
        _engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=pool_overflow,
            echo=False,
        )

    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    log.info(f"Database engine initialized: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    return _engine


def get_engine() -> AsyncEngine:
    """Get the current engine (must be initialized first)."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")
    return _engine


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Short-lived async session context manager.

    Usage:
        async with get_db_session() as session:
            result = await session.execute(...)
    """
    if _session_factory is None:
        raise RuntimeError("Database engine not initialized. Call init_engine() first.")

    session = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def close_engine() -> None:
    """Close the engine and release all connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        log.info("Database engine closed")
