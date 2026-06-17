"""Tests for auth/quota.py quota enforcement."""
import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Lightweight config stub carrying only the quota fields we care about
# ---------------------------------------------------------------------------

class _FakeConfig:
    max_containers_per_user: int = 5
    max_sessions_per_user: int = 200
    max_concurrent_agents: int = 3
    monthly_cost_limit: float = 50.0


@pytest.fixture
def config():
    return _FakeConfig()


# ── check_container_quota ──────────────────────────────────────────────────

async def test_container_quota_under_limit(config):
    repo = AsyncMock()
    repo.count_by_user.return_value = 3

    with patch("db.repository.container_repo.PgContainerRepo", return_value=repo):
        from auth.quota import check_container_quota
        await check_container_quota("user1", config)  # should not raise


async def test_container_quota_at_limit_raises(config):
    repo = AsyncMock()
    repo.count_by_user.return_value = 5

    with patch("db.repository.container_repo.PgContainerRepo", return_value=repo):
        from auth.quota import check_container_quota
        with pytest.raises(HTTPException) as exc_info:
            await check_container_quota("user1", config)
        assert exc_info.value.status_code == 429
        assert "Container quota" in exc_info.value.detail


async def test_container_quota_over_limit_raises(config):
    repo = AsyncMock()
    repo.count_by_user.return_value = 10

    with patch("db.repository.container_repo.PgContainerRepo", return_value=repo):
        from auth.quota import check_container_quota
        with pytest.raises(HTTPException) as exc_info:
            await check_container_quota("user1", config)
        assert exc_info.value.status_code == 429


# ── check_session_quota ────────────────────────────────────────────────────

async def test_session_quota_under_limit(config):
    repo = AsyncMock()
    repo.count_by_user.return_value = 50

    with patch("db.repository.session_repo.PgSessionRepo", return_value=repo):
        from auth.quota import check_session_quota
        await check_session_quota("user1", config)  # should not raise


async def test_session_quota_at_limit_raises(config):
    repo = AsyncMock()
    repo.count_by_user.return_value = 200

    with patch("db.repository.session_repo.PgSessionRepo", return_value=repo):
        from auth.quota import check_session_quota
        with pytest.raises(HTTPException) as exc_info:
            await check_session_quota("user1", config)
        assert exc_info.value.status_code == 429
        assert "Session quota" in exc_info.value.detail


# ── check_concurrent_agents ────────────────────────────────────────────────

async def test_concurrent_agents_under_limit(config):
    repo = AsyncMock()
    repo.count_busy.return_value = 1

    with patch("db.repository.session_repo.PgSessionRepo", return_value=repo):
        from auth.quota import check_concurrent_agents
        await check_concurrent_agents("user1", config)  # should not raise


async def test_concurrent_agents_at_limit_raises(config):
    repo = AsyncMock()
    repo.count_busy.return_value = 3

    with patch("db.repository.session_repo.PgSessionRepo", return_value=repo):
        from auth.quota import check_concurrent_agents
        with pytest.raises(HTTPException) as exc_info:
            await check_concurrent_agents("user1", config)
        assert exc_info.value.status_code == 429
        assert "Concurrent agent" in exc_info.value.detail


# ── check_monthly_cost ─────────────────────────────────────────────────────

async def test_monthly_cost_under_limit(config):
    repo = AsyncMock()
    repo.sum_cost_this_month.return_value = 25.0

    with patch("db.repository.message_repo.PgMessageRepo", return_value=repo):
        from auth.quota import check_monthly_cost
        await check_monthly_cost("user1", config)  # should not raise


async def test_monthly_cost_at_limit_raises(config):
    repo = AsyncMock()
    repo.sum_cost_this_month.return_value = 50.0

    with patch("db.repository.message_repo.PgMessageRepo", return_value=repo):
        from auth.quota import check_monthly_cost
        with pytest.raises(HTTPException) as exc_info:
            await check_monthly_cost("user1", config)
        assert exc_info.value.status_code == 429
        assert "Monthly cost" in exc_info.value.detail


async def test_monthly_cost_over_limit_raises(config):
    repo = AsyncMock()
    repo.sum_cost_this_month.return_value = 99.99

    with patch("db.repository.message_repo.PgMessageRepo", return_value=repo):
        from auth.quota import check_monthly_cost
        with pytest.raises(HTTPException) as exc_info:
            await check_monthly_cost("user1", config)
        assert exc_info.value.status_code == 429


# ── Edge cases ─────────────────────────────────────────────────────────────

async def test_container_quota_zero_is_under_limit(config):
    repo = AsyncMock()
    repo.count_by_user.return_value = 0

    with patch("db.repository.container_repo.PgContainerRepo", return_value=repo):
        from auth.quota import check_container_quota
        await check_container_quota("user1", config)  # should not raise


async def test_monthly_cost_zero_is_under_limit(config):
    repo = AsyncMock()
    repo.sum_cost_this_month.return_value = 0.0

    with patch("db.repository.message_repo.PgMessageRepo", return_value=repo):
        from auth.quota import check_monthly_cost
        await check_monthly_cost("user1", config)  # should not raise


async def test_custom_limits(config):
    """Verify that custom config limits are respected, not just defaults."""
    config.max_containers_per_user = 2

    repo = AsyncMock()
    repo.count_by_user.return_value = 2

    with patch("db.repository.container_repo.PgContainerRepo", return_value=repo):
        from auth.quota import check_container_quota
        with pytest.raises(HTTPException) as exc_info:
            await check_container_quota("user1", config)
        assert exc_info.value.status_code == 429
        assert "2/2" in exc_info.value.detail
