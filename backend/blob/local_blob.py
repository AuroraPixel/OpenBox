"""Local filesystem implementation of IBlobStorage — for development/testing."""
import json
import os
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from core.log import create_logger

log = create_logger("blob.local")


class LocalBlobStorage:
    def __init__(self, base_path: str = "/opt/openbox/blobs"):
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)
        log.info(f"Local blob storage at: {self._base}")

    def _path(self, key: str) -> Path:
        return self._base / key

    def _meta_path(self, key: str) -> Path:
        return self._base / f"{key}.__meta__.json"

    async def upload(self, key: str, data: bytes | AsyncIterator[bytes],
                     metadata: dict | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            async with aiofiles.open(path, "wb") as f:
                await f.write(data)
        else:
            async with aiofiles.open(path, "wb") as f:
                async for chunk in data:
                    await f.write(chunk)
        if metadata:
            async with aiofiles.open(self._meta_path(key), "w") as f:
                await f.write(json.dumps(metadata))
        return key

    async def download(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(65536):
                yield chunk

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()
        meta = self._meta_path(key)
        if meta.exists():
            meta.unlink()

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def list_keys(self, prefix: str) -> list[str]:
        prefix_path = self._base / prefix
        if not prefix_path.parent.exists():
            return []
        keys = []
        base_str = str(self._base) + "/"
        for root, dirs, files in os.walk(str(prefix_path.parent)):
            for f in files:
                if f.endswith(".__meta__.json"):
                    continue
                full = os.path.join(root, f)
                rel = full[len(base_str):]
                if rel.startswith(prefix):
                    keys.append(rel)
        return keys

    async def get_metadata(self, key: str) -> dict | None:
        meta = self._meta_path(key)
        if not meta.exists():
            return None
        async with aiofiles.open(meta, "r") as f:
            return json.loads(await f.read())

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        return f"file://{self._path(key)}"

    async def close(self) -> None:
        pass
