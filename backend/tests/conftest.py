"""Shared test fixtures for all tests."""
import asyncio
import pytest
from db.base import Base, init_engine, close_engine, get_db_session


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def ensure_test_db():
    """Ensure a test database engine exists for every test.

    Re-initializes if the engine was closed (e.g., by integration test teardown).
    """
    from db.base import _engine
    if _engine is None:
        engine = init_engine("sqlite+aiosqlite:///:memory:")
        import db.models  # noqa: F401
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def db_session():
    """Get a test database session."""
    async with get_db_session() as session:
        yield session
