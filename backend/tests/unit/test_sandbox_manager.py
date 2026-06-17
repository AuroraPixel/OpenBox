"""Tests for sandbox manager health check and stale container cleanup."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from sandbox.manager import SandboxManager, SandboxInfo, _map_key
from sandbox.client import SandboxClient


@pytest.fixture
def manager():
    return SandboxManager()


@pytest.fixture
def sandbox_info():
    return SandboxInfo(
        container_id="abc123",
        host="localhost",
        port=9000,
        api_key="test-key",
        project_id="proj1",
        session_ids={"sess1"},
        user_id="user1",
    )


# ── _verify_sandbox_alive ──

@pytest.mark.asyncio
async def test_verify_alive_returns_true_when_healthy(manager, sandbox_info):
    """Container responding 200 on /alive should be considered alive."""
    key = _map_key("user1", "proj1")
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await manager._verify_sandbox_alive(sandbox_info, key)
        assert result is True


@pytest.mark.asyncio
async def test_verify_alive_returns_false_when_connection_fails(manager, sandbox_info):
    """Connection error should make verify return False."""
    key = _map_key("user1", "proj1")
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await manager._verify_sandbox_alive(sandbox_info, key)
        assert result is False


@pytest.mark.asyncio
async def test_verify_alive_returns_false_on_non_200(manager, sandbox_info):
    """Non-200 status should make verify return False."""
    key = _map_key("user1", "proj1")
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await manager._verify_sandbox_alive(sandbox_info, key)
        assert result is False


# ── _cleanup_stale_sandbox ──

@pytest.mark.asyncio
async def test_cleanup_stale_sandbox_clears_all_state(manager, sandbox_info):
    """Cleanup should remove sandbox from all manager and provider tracking."""
    key = _map_key("user1", "proj1")
    manager._project_map[key] = sandbox_info
    manager._clients[key] = MagicMock()
    manager._session_project["sess1"] = key
    manager._session_project["sess2"] = key

    mock_provider = MagicMock()
    mock_provider._containers = {"abc123": MagicMock()}
    mock_provider._api_keys = {"abc123": "key"}
    mock_provider._container_owners = {"abc123": "user1"}
    mock_provider._container_projects = {"abc123": "proj1"}

    with patch("sandbox.provider", mock_provider):
        await manager._cleanup_stale_sandbox(sandbox_info, key, "sess1")

    assert key not in manager._project_map
    assert key not in manager._clients
    assert "sess1" not in manager._session_project
    assert "sess2" not in manager._session_project
    assert "abc123" not in mock_provider._containers
    assert "abc123" not in mock_provider._api_keys
    assert "abc123" not in mock_provider._container_owners
    assert "abc123" not in mock_provider._container_projects


# ── acquire() with dead container ──

@pytest.mark.asyncio
async def test_acquire_detects_dead_container_in_project_map(manager, sandbox_info):
    """acquire() should detect a dead container and create a new one."""
    key = _map_key("user1", "default")
    # Pre-populate with a dead sandbox
    sandbox_info.project_id = "default"
    manager._project_map[key] = sandbox_info
    manager._clients[key] = MagicMock()
    manager._session_project["sess1"] = key

    # Mock _verify_sandbox_alive to return False (dead container)
    async def mock_verify(sb, k):
        return False

    manager._verify_sandbox_alive = mock_verify

    mock_info = MagicMock()
    mock_info.id = "new123"
    mock_info.host = "localhost"
    mock_info.port = 9001
    mock_info.api_key = "new-key"

    mock_provider = MagicMock()
    mock_provider._containers = {"abc123": MagicMock()}
    mock_provider._api_keys = {"abc123": "key"}
    mock_provider._container_owners = {"abc123": "user1"}
    mock_provider._container_projects = {"abc123": "default"}
    mock_provider.get_user_container = MagicMock(return_value=None)
    mock_provider.create_container = AsyncMock(return_value=mock_info)

    manager._ensure_session_dir = AsyncMock()

    with patch("sandbox.provider", mock_provider):
        result = await manager.acquire("sess1", "default", user_id="user1")

    assert result.container_id == "new123"
    assert result.port == 9001


@pytest.mark.asyncio
async def test_acquire_reuses_alive_container(manager, sandbox_info):
    """acquire() should reuse container when it's alive."""
    key = _map_key("user1", "default")
    sandbox_info.project_id = "default"
    manager._project_map[key] = sandbox_info
    manager._clients[key] = MagicMock()

    manager._verify_sandbox_alive = AsyncMock(return_value=True)
    manager._ensure_session_dir = AsyncMock()

    result = await manager.acquire("sess2", "default", user_id="user1")

    assert result.container_id == "abc123"
    assert "sess2" in result.session_ids


@pytest.mark.asyncio
async def test_acquire_does_not_reuse_other_users_container(manager, sandbox_info):
    """acquire() must NOT reuse a container belonging to a different user."""
    key_user1 = _map_key("user1", "default")
    sandbox_info.project_id = "default"
    manager._project_map[key_user1] = sandbox_info
    manager._clients[key_user1] = MagicMock()

    manager._verify_sandbox_alive = AsyncMock(return_value=True)
    manager._ensure_session_dir = AsyncMock()

    mock_info = MagicMock()
    mock_info.id = "user2container"
    mock_info.host = "localhost"
    mock_info.port = 9002
    mock_info.api_key = "user2-key"

    mock_provider = MagicMock()
    mock_provider.get_user_container = MagicMock(return_value=None)
    mock_provider.create_container = AsyncMock(return_value=mock_info)

    with patch("sandbox.provider", mock_provider):
        result = await manager.acquire("sess-user2", "default", user_id="user2")

    # user2 should get their own container, NOT user1's
    assert result.container_id == "user2container"
    assert result.user_id == "user2"


# ── get_client() with dead container ──

@pytest.mark.asyncio
async def test_get_client_re_acquires_when_dead(manager, sandbox_info):
    """get_client() should re-acquire when existing sandbox is dead."""
    key = _map_key("user1", "default")
    sandbox_info.project_id = "default"
    manager._project_map[key] = sandbox_info
    old_client = MagicMock(spec=SandboxClient)
    manager._clients[key] = old_client
    manager._session_project["sess1"] = key

    verify_call_count = 0

    async def mock_verify(sb, k):
        nonlocal verify_call_count
        verify_call_count += 1
        if verify_call_count == 1:
            return False  # Dead on first check
        return True  # Alive after re-acquire

    manager._verify_sandbox_alive = mock_verify

    mock_provider_obj = MagicMock()
    mock_provider_obj._containers = {"abc123": MagicMock()}
    mock_provider_obj._api_keys = {"abc123": "key"}
    mock_provider_obj._container_owners = {"abc123": "user1"}
    mock_provider_obj._container_projects = {"abc123": "default"}
    mock_provider_obj.get_user_container = MagicMock(return_value=None)

    new_info = MagicMock()
    new_info.id = "new456"
    new_info.host = "localhost"
    new_info.port = 9002
    new_info.api_key = "new-key2"
    mock_provider_obj.create_container = AsyncMock(return_value=new_info)

    manager._ensure_session_dir = AsyncMock()

    with patch("sandbox.provider", mock_provider_obj):
        client = await manager.get_client("sess1", user_id="user1")

    # Should have gotten a new client (not the old dead one)
    assert client is not old_client
    assert key in manager._clients
