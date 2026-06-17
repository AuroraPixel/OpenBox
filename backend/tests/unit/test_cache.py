"""Test MemoryCache implementation."""
import asyncio
import pytest
from cache.memory_cache import MemoryCache


@pytest.fixture
def cache():
    return MemoryCache()


async def test_get_set(cache):
    await cache.set("key1", {"hello": "world"})
    result = await cache.get("key1")
    assert result == {"hello": "world"}


async def test_get_missing(cache):
    result = await cache.get("nonexistent")
    assert result is None


async def test_ttl_expiry(cache):
    await cache.set("key1", "value", ttl=1)
    assert await cache.get("key1") == "value"
    await asyncio.sleep(1.1)
    assert await cache.get("key1") is None


async def test_delete(cache):
    await cache.set("key1", "value")
    await cache.delete("key1")
    assert await cache.get("key1") is None


async def test_delete_pattern(cache):
    await cache.set("sessions:user1:proj1", "a")
    await cache.set("sessions:user1:proj2", "b")
    await cache.set("sessions:user2:proj1", "c")
    await cache.delete_pattern("sessions:user1:*")
    assert await cache.get("sessions:user1:proj1") is None
    assert await cache.get("sessions:user1:proj2") is None
    assert await cache.get("sessions:user2:proj1") == "c"


async def test_exists(cache):
    assert await cache.exists("key1") is False
    await cache.set("key1", "value")
    assert await cache.exists("key1") is True


async def test_incr(cache):
    v1 = await cache.incr("counter")
    assert v1 == 1
    v2 = await cache.incr("counter")
    assert v2 == 2
    v3 = await cache.incr("counter")
    assert v3 == 3


async def test_incr_with_ttl(cache):
    v1 = await cache.incr("rate:login", ttl=1)
    assert v1 == 1
    await asyncio.sleep(1.1)
    v2 = await cache.incr("rate:login", ttl=1)
    assert v2 == 1  # Reset after TTL
