"""Cache abstraction layer — Protocol interface."""
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ICache(Protocol):
    async def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None if not found or expired."""
        ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set a cached value with optional TTL in seconds."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a cached value."""
        ...

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern (e.g., 'sessions:uid:*')."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        ...

    async def incr(self, key: str, ttl: int | None = None) -> int:
        """Atomically increment a counter. Create with value 1 if not exists."""
        ...
