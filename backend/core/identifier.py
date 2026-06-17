"""ULID-based ID generation for sessions, messages, and parts."""
import time
from ulid import ULID


def ascending(prefix: str) -> str:
    """Generate a time-ordered ascending ID (newer IDs sort later).
    Used for messages, parts, etc."""
    return f"{prefix}_{ULID()}"


def descending(prefix: str, custom_id: str | None = None) -> str:
    """Generate a time-ordered descending ID (newer IDs sort first).
    Used for sessions so newest appears first in storage listing."""
    if custom_id:
        return f"{prefix}_{custom_id}"
    # Invert timestamp bits for descending order
    ulid = ULID()
    ts = ulid.timestamp
    # Max ULID timestamp (2^48 - 1 milliseconds)
    max_ts = (1 << 48) - 1
    inverted_ms = max_ts - int(ts * 1000)
    # Create new ULID with inverted timestamp
    inverted_ulid = ULID.from_int((inverted_ms << 80) | (int(ulid) & ((1 << 80) - 1)))
    return f"{prefix}_{inverted_ulid}"


def generate_id() -> str:
    """Generate a simple unique ID."""
    return str(ULID())
