"""In-memory implementation of ICache — for development and testing only."""
import asyncio
import fnmatch
import time
from typing import Any


class MemoryCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, float | None]] = {}  # key -> (value, expires_at)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at and time.time() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = (time.time() + ttl) if ttl else None
        async with self._lock:
            self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> None:
        async with self._lock:
            keys_to_delete = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
            for k in keys_to_delete:
                del self._store[k]

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def incr(self, key: str, ttl: int | None = None) -> int:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None or (entry[1] and time.time() > entry[1]):
                expires_at = (time.time() + ttl) if ttl else None
                self._store[key] = (1, expires_at)
                return 1
            value = entry[0] + 1
            self._store[key] = (value, entry[1])
            return value

    async def close(self) -> None:
        self._store.clear()
