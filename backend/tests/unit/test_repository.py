"""Test Repository basic CRUD with SQLite in-memory."""
import pytest
from core.identifier import generate_id
from db.repository.user_repo import PgUserRepo


@pytest.fixture
def user_repo():
    return PgUserRepo()


async def test_create_and_get_user(user_repo):
    uid = generate_id()
    result = await user_repo.create(
        id=uid, username="testuser", password_hash="hashed", email="test@example.com"
    )
    assert result["username"] == "testuser"

    user = await user_repo.get(uid)
    assert user is not None
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["role"] == "user"


async def test_get_by_username(user_repo):
    uid = generate_id()
    await user_repo.create(id=uid, username="findme", password_hash="hashed")
    user = await user_repo.get_by_username("findme")
    assert user is not None
    assert user["id"] == uid


async def test_get_nonexistent(user_repo):
    user = await user_repo.get("nonexistent_id_12345678")
    assert user is None


async def test_soft_delete(user_repo):
    uid = generate_id()
    await user_repo.create(id=uid, username="deleteme", password_hash="hashed")
    await user_repo.soft_delete(uid)
    user = await user_repo.get(uid)
    assert user is None  # Soft-deleted users should not be returned


async def test_increment_failed_login(user_repo):
    uid = generate_id()
    await user_repo.create(id=uid, username="locktest", password_hash="hashed")
    count = await user_repo.increment_failed_login(uid)
    assert count == 1
    count = await user_repo.increment_failed_login(uid)
    assert count == 2
