"""Integration test for auth API — register, login, refresh, token validation."""
import os
import pytest
from httpx import AsyncClient, ASGITransport

# Set env vars before any imports
os.environ["JWT_SECRET"] = "test-integration-secret-32bytes!!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


_test_cache = None


@pytest.fixture(scope="module")
async def app():
    """Create app with auth enabled, using in-memory SQLite + MemoryCache."""
    global _test_cache
    from cache.memory_cache import MemoryCache
    _test_cache = MemoryCache()

    # Force reload config to pick up env vars
    from core.config import reload_config
    config = reload_config()

    from db.base import init_engine, Base, close_engine
    engine = init_engine("sqlite+aiosqlite:///:memory:")
    import db.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from auth import setup_auth
    setup_auth(config, _test_cache)

    from main import create_app
    application = create_app()
    yield application

    await close_engine()


@pytest.fixture
async def client(app):
    # Clear rate limit cache before each test
    if _test_cache:
        await _test_cache.close()
        _test_cache._store.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_register(client):
    resp = await client.post("/api/auth/register", json={
        "username": "testuser1",
        "password": "password123",
        "email": "test@example.com",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["username"] == "testuser1"
    assert "password_hash" not in data["user"]


async def test_register_weak_password(client):
    resp = await client.post("/api/auth/register", json={
        "username": "weakuser",
        "password": "short",
    })
    assert resp.status_code == 400


async def test_register_duplicate_username(client):
    await client.post("/api/auth/register", json={
        "username": "dupuser1",
        "password": "password123",
    })
    resp = await client.post("/api/auth/register", json={
        "username": "dupuser1",
        "password": "password456",
    })
    assert resp.status_code == 409


async def test_login_success(client):
    # Register
    reg = await client.post("/api/auth/register", json={
        "username": "loginuser1",
        "password": "mypassword1",
    })
    assert reg.status_code == 200, reg.text

    # Login
    resp = await client.post("/api/auth/login", json={
        "username": "loginuser1",
        "password": "mypassword1",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data


async def test_login_wrong_password(client):
    await client.post("/api/auth/register", json={
        "username": "wrongpw1",
        "password": "correct123",
    })
    resp = await client.post("/api/auth/login", json={
        "username": "wrongpw1",
        "password": "wrong123",
    })
    assert resp.status_code == 401


async def test_me_with_token(client):
    resp = await client.post("/api/auth/register", json={
        "username": "meuser1",
        "password": "password123",
    })
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "meuser1"


async def test_me_without_token(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


async def test_ticket(client):
    resp = await client.post("/api/auth/register", json={
        "username": "ticketuser1",
        "password": "password123",
    })
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    resp = await client.post("/api/auth/ticket", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    ticket = resp.json()["ticket"]
    assert len(ticket) > 20
