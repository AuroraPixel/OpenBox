"""Storage layer — DB-backed when database is initialized, file-system fallback otherwise.

This module preserves the original read/write/list_keys/remove interface
so all 30+ calling sites work unchanged, while routing data through PostgreSQL
when the database engine is available (multi-user mode).
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, TypeVar

import aiofiles

from core.log import create_logger

log = create_logger("storage")

T = TypeVar("T")

# Default base directory (XDG compliant) — used for file-system fallback
_base_dir: Path | None = None
_lock = asyncio.Lock()


def _use_db() -> bool:
    """Check if DB engine is available."""
    try:
        from db.base import _engine
        return _engine is not None
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# DB-backed implementation
# ---------------------------------------------------------------------------

async def _db_read(key: list[str]) -> Any | None:
    """Read from the kv_store table in the database."""
    from db.base import get_db_session
    from sqlalchemy import text
    db_key = "/".join(key)
    async with get_db_session() as session:
        result = await session.execute(
            text("SELECT value FROM kv_store WHERE key = :key"),
            {"key": db_key},
        )
        row = result.first()
        if row:
            return json.loads(row[0])
        return None


async def _db_write(key: list[str], content: Any) -> None:
    """Write to the kv_store table (upsert)."""
    from db.base import get_db_session
    from sqlalchemy import text
    db_key = "/".join(key)
    value = json.dumps(content, default=str, ensure_ascii=False)
    async with get_db_session() as session:
        # Upsert: try update first, then insert
        result = await session.execute(
            text("UPDATE kv_store SET value = :value, updated_at = NOW() WHERE key = :key"),
            {"key": db_key, "value": value},
        )
        if result.rowcount == 0:
            await session.execute(
                text("INSERT INTO kv_store (key, value, updated_at) VALUES (:key, :value, NOW())"),
                {"key": db_key, "value": value},
            )


async def _db_remove(key: list[str]) -> None:
    """Delete from the kv_store table."""
    from db.base import get_db_session
    from sqlalchemy import text
    db_key = "/".join(key)
    async with get_db_session() as session:
        await session.execute(
            text("DELETE FROM kv_store WHERE key = :key"),
            {"key": db_key},
        )


async def _db_list_keys(prefix: list[str]) -> list[list[str]]:
    """List keys with a given prefix from the kv_store table."""
    from db.base import get_db_session
    from sqlalchemy import text
    db_prefix = "/".join(prefix) + "/" if prefix else ""
    async with get_db_session() as session:
        result = await session.execute(
            text("SELECT key FROM kv_store WHERE key LIKE :prefix ORDER BY key"),
            {"prefix": f"{db_prefix}%"},
        )
        return [row[0].split("/") for row in result.fetchall()]


# ---------------------------------------------------------------------------
# File-system implementation (original, for single-user / no-DB mode)
# ---------------------------------------------------------------------------

def get_base_dir() -> Path:
    global _base_dir
    if _base_dir is None:
        data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        _base_dir = Path(data_home) / "openbox" / "storage"
    return _base_dir


def set_base_dir(path: Path) -> None:
    global _base_dir
    _base_dir = path


def _key_to_path_str(key: list[str]) -> Path:
    base = get_base_dir()
    return base / Path(*key).with_suffix(".json")


async def _fs_read(key: list[str]) -> Any | None:
    path = _key_to_path_str(key)
    if not path.exists():
        return None
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return json.loads(content)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        log.warning(f"Failed to read {path}: {e}")
        return None


async def _fs_write(key: list[str], content: Any) -> None:
    path = _key_to_path_str(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(content, default=str, ensure_ascii=False, indent=2)
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(data)


async def _fs_remove(key: list[str]) -> None:
    path = _key_to_path_str(key)
    try:
        if path.exists():
            path.unlink()
    except OSError as e:
        log.warning(f"Failed to remove {path}: {e}")


async def _fs_list_keys(prefix: list[str]) -> list[list[str]]:
    base = get_base_dir()
    prefix_path = base / Path(*prefix) if prefix else base
    if not prefix_path.exists():
        return []
    result = []
    for item in sorted(prefix_path.iterdir()):
        if item.is_file() and item.suffix == ".json":
            relative = item.relative_to(base)
            key = list(relative.with_suffix("").parts)
            result.append(key)
        elif item.is_dir():
            for sub in sorted(item.iterdir()):
                if sub.is_file() and sub.suffix == ".json":
                    relative = sub.relative_to(base)
                    key = list(relative.with_suffix("").parts)
                    result.append(key)
    return result


# ---------------------------------------------------------------------------
# Public API — routes to DB or filesystem based on availability
# ---------------------------------------------------------------------------

async def read(key: list[str]) -> Any | None:
    if _use_db():
        return await _db_read(key)
    return await _fs_read(key)


async def write(key: list[str], content: Any) -> None:
    if _use_db():
        await _db_write(key, content)
    else:
        await _fs_write(key, content)


async def update(key: list[str], fn: Callable[[Any], Any]) -> Any:
    async with _lock:
        current = await read(key)
        if current is None:
            current = {}
        result = fn(current)
        if result is None:
            result = current
        await write(key, result)
        return result


async def remove(key: list[str]) -> None:
    if _use_db():
        await _db_remove(key)
    else:
        await _fs_remove(key)


async def list_keys(prefix: list[str]) -> list[list[str]]:
    if _use_db():
        return await _db_list_keys(prefix)
    return await _fs_list_keys(prefix)
