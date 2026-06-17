"""Redis implementation of ICache."""
import json
from typing import Any

import redis.asyncio as aioredis

from core.log import create_logger

log = create_logger("cache.redis")


class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=True
        )

    async def get(self, key: str) -> Any | None:
        value = await self._redis.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            await self._redis.setex(key, ttl, serialized)
        else:
            await self._redis.set(key, serialized)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))

    async def incr(self, key: str, ttl: int | None = None) -> int:
        value = await self._redis.incr(key)
        if ttl and value == 1:
            await self._redis.expire(key, ttl)
        return value

    async def publish(self, channel: str, message: str) -> None:
        await self._redis.publish(channel, message)

    def subscribe(self, *channels: str):
        return self._redis.pubsub()

    async def close(self) -> None:
        await self._redis.aclose()
        log.info("Redis connection closed")

    @property
    def redis(self) -> aioredis.Redis:
        return self._redis
