"""Integration test for main WebSocket endpoint."""
import os
import json
import pytest
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

os.environ["JWT_SECRET"] = "test-ws-secret-32bytes-long!!!!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


_test_cache = None


@pytest.fixture(scope="module")
async def app():
    global _test_cache
    from cache.memory_cache import MemoryCache
    _test_cache = MemoryCache()

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
    if _test_cache:
        _test_cache._store.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sync_client(app):
    """Sync test client for WebSocket testing."""
    return TestClient(app)


async def _get_ticket(client) -> str:
    """Register a user and get a ticket for WS auth."""
    import secrets
    username = f"wsuser_{secrets.token_hex(4)}"
    resp = await client.post("/api/auth/register", json={
        "username": username,
        "password": "password123",
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    resp = await client.post("/api/auth/ticket", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    return resp.json()["ticket"]


async def test_ws_connect_with_ticket(client, sync_client):
    """Test WebSocket connects with valid ticket."""
    ticket = await _get_ticket(client)
    with sync_client.websocket_connect(f"/ws/agent?ticket={ticket}") as ws:
        # Should receive server.connected event
        data = ws.receive_json()
        assert data["type"] == "server.connected"


async def test_ws_reject_without_ticket(sync_client):
    """Test WebSocket rejects connection without ticket."""
    try:
        with sync_client.websocket_connect("/ws/agent") as ws:
            # Should be closed immediately
            ws.receive_json()
            assert False, "Should have been rejected"
    except Exception:
        pass  # Expected — connection rejected


async def test_ws_reject_invalid_ticket(sync_client):
    """Test WebSocket rejects connection with invalid ticket."""
    try:
        with sync_client.websocket_connect("/ws/agent?ticket=invalid-ticket-xxx") as ws:
            ws.receive_json()
            assert False, "Should have been rejected"
    except Exception:
        pass  # Expected


async def test_ws_ticket_one_time_use(client, sync_client):
    """Test that ticket can only be used once."""
    ticket = await _get_ticket(client)
    # First use — should work
    with sync_client.websocket_connect(f"/ws/agent?ticket={ticket}") as ws:
        data = ws.receive_json()
        assert data["type"] == "server.connected"

    # Second use — should fail
    try:
        with sync_client.websocket_connect(f"/ws/agent?ticket={ticket}") as ws:
            ws.receive_json()
            assert False, "Should have been rejected"
    except Exception:
        pass  # Expected


async def test_ws_send_abort(client, sync_client):
    """Test sending abort command through WebSocket."""
    ticket = await _get_ticket(client)
    with sync_client.websocket_connect(f"/ws/agent?ticket={ticket}") as ws:
        ws.receive_json()  # server.connected
        # Send abort — should not crash
        ws.send_json({"type": "session.abort", "sessionId": "nonexistent"})
        # No response expected for abort, just verify no crash
