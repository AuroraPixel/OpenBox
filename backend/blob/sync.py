"""Blob sync service -- local cache <-> remote blob storage.

Handles bidirectional synchronization between local bind mounts and
remote blob storage, using a manifest to track file state (mtime, size).
"""
import asyncio
import fnmatch
import json
import os
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from core.log import create_logger

log = create_logger("blob.sync")

# Base path for local project caches — must match docker.py bind mount path
_data_home = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
LOCAL_CACHE_BASE = Path(_data_home) / "openbox" / "cache"

# Default patterns to exclude from sync
DEFAULT_EXCLUDE_PATTERNS = [
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "dist/",
    "build/",
    "*.pyc",
    "*.o",
    "*.so",
    ".git/objects/pack/",
    ".DS_Store",
    "*.tmp",
    "*.log",
    ".env",
]


def _blob_prefix(user_id: str, project_id: str) -> str:
    """Return the blob key prefix for a user/project."""
    return f"projects/{user_id}/{project_id}/"


def _manifest_key(user_id: str, project_id: str) -> str:
    """Return the blob key for the manifest file."""
    return f"projects/{user_id}/{project_id}/.manifest.json"


def _local_path(user_id: str, project_id: str) -> Path:
    """Return the local cache path for a user/project."""
    return LOCAL_CACHE_BASE / user_id / project_id


def _should_exclude(rel_path: str, exclude_patterns: list[str]) -> bool:
    """Check if a relative path matches any exclude pattern."""
    parts = rel_path.split("/")
    for pattern in exclude_patterns:
        # Directory pattern (ends with /)
        if pattern.endswith("/"):
            dir_name = pattern.rstrip("/")
            if dir_name in parts:
                return True
        # File glob pattern
        elif fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        # Full path glob
        elif fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def _scan_local_files(base: Path, exclude_patterns: list[str]) -> dict[str, dict[str, Any]]:
    """Scan local directory and return a manifest dict of {rel_path: {mtime, size}}."""
    manifest: dict[str, dict[str, Any]] = {}
    if not base.exists():
        return manifest

    for root, dirs, files in os.walk(str(base)):
        # Prune excluded directories in-place for efficiency
        dirs[:] = [
            d for d in dirs
            if not _should_exclude(d + "/", exclude_patterns)
        ]

        for fname in files:
            full_path = Path(root) / fname
            rel_path = str(full_path.relative_to(base))

            if _should_exclude(rel_path, exclude_patterns):
                continue

            try:
                stat = full_path.stat()
                manifest[rel_path] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            except OSError:
                # File may have been deleted between walk and stat
                continue

    return manifest


class BlobSyncService:
    """Manages bidirectional sync between local bind mounts and remote blob storage."""

    def __init__(self, blob_storage, exclude_patterns: list[str] | None = None):
        self._blob = blob_storage
        self._exclude = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
        self._periodic_tasks: dict[str, asyncio.Task] = {}

    async def _read_remote_manifest(self, user_id: str, project_id: str) -> dict[str, dict[str, Any]]:
        """Download and parse the manifest from blob storage."""
        key = _manifest_key(user_id, project_id)
        try:
            if not await self._blob.exists(key):
                return {}
            chunks = []
            async for chunk in self._blob.download(key):
                chunks.append(chunk)
            data = b"".join(chunks)
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            log.warning(f"Could not read manifest for {user_id}/{project_id}: {e}")
            return {}

    async def _write_remote_manifest(self, user_id: str, project_id: str,
                                     manifest: dict[str, dict[str, Any]]) -> None:
        """Upload the manifest to blob storage."""
        key = _manifest_key(user_id, project_id)
        data = json.dumps(manifest, indent=2).encode("utf-8")
        await self._blob.upload(key, data)

    async def restore(self, user_id: str, project_id: str) -> bool:
        """Download files from blob storage to local path.

        Returns True if data was restored.
        """
        local_dir = _local_path(user_id, project_id)
        prefix = _blob_prefix(user_id, project_id)

        # Read remote manifest to know what files exist
        manifest = await self._read_remote_manifest(user_id, project_id)
        if not manifest:
            # No manifest means nothing was backed up yet; check for any files
            keys = await self._blob.list_keys(prefix)
            # Filter out manifest key itself
            keys = [k for k in keys if not k.endswith(".manifest.json")]
            if not keys:
                log.info(f"No data to restore for {user_id}/{project_id}")
                return False

        local_dir.mkdir(parents=True, exist_ok=True)
        restored_count = 0

        # Download files listed in manifest
        for rel_path, meta in manifest.items():
            blob_key = prefix + rel_path
            local_file = local_dir / rel_path

            try:
                local_file.parent.mkdir(parents=True, exist_ok=True)
                chunks = []
                async for chunk in self._blob.download(blob_key):
                    chunks.append(chunk)

                async with aiofiles.open(local_file, "wb") as f:
                    for chunk in chunks:
                        await f.write(chunk)

                # Restore mtime if available
                if "mtime" in meta:
                    os.utime(str(local_file), (meta["mtime"], meta["mtime"]))

                restored_count += 1
            except Exception as e:
                log.warning(f"Failed to restore {rel_path}: {e}")

        log.info(f"Restored {restored_count} file(s) for {user_id}/{project_id}")
        return restored_count > 0

    async def backup(self, user_id: str, project_id: str) -> bool:
        """Incremental sync local -> blob.

        Compares local file mtime/size with the remote manifest and uploads
        only changed or new files. Returns True if any files were synced.
        """
        local_dir = _local_path(user_id, project_id)
        prefix = _blob_prefix(user_id, project_id)

        if not local_dir.exists():
            log.info(f"No local data to back up for {user_id}/{project_id}")
            return False

        # Scan local files
        local_manifest = _scan_local_files(local_dir, self._exclude)

        # Read remote manifest
        remote_manifest = await self._read_remote_manifest(user_id, project_id)

        # Determine which files need uploading (new or changed)
        to_upload: list[str] = []
        for rel_path, local_meta in local_manifest.items():
            remote_meta = remote_manifest.get(rel_path)
            if remote_meta is None:
                # New file
                to_upload.append(rel_path)
            elif (local_meta["mtime"] != remote_meta.get("mtime")
                  or local_meta["size"] != remote_meta.get("size")):
                # Changed file
                to_upload.append(rel_path)

        # Determine which remote files need deleting (no longer local)
        to_delete: list[str] = []
        for rel_path in remote_manifest:
            if rel_path not in local_manifest:
                to_delete.append(rel_path)

        if not to_upload and not to_delete:
            log.debug(f"No changes to back up for {user_id}/{project_id}")
            return False

        # Upload changed files
        uploaded = 0
        for rel_path in to_upload:
            blob_key = prefix + rel_path
            local_file = local_dir / rel_path
            try:
                async with aiofiles.open(local_file, "rb") as f:
                    data = await f.read()
                await self._blob.upload(blob_key, data)
                uploaded += 1
            except Exception as e:
                log.warning(f"Failed to upload {rel_path}: {e}")

        # Delete removed files from blob
        deleted = 0
        for rel_path in to_delete:
            blob_key = prefix + rel_path
            try:
                await self._blob.delete(blob_key)
                deleted += 1
            except Exception as e:
                log.warning(f"Failed to delete {rel_path} from blob: {e}")

        # Write updated manifest
        await self._write_remote_manifest(user_id, project_id, local_manifest)

        log.info(
            f"Backup for {user_id}/{project_id}: "
            f"{uploaded} uploaded, {deleted} deleted"
        )
        return True

    async def cleanup_local(self, user_id: str, project_id: str) -> None:
        """Remove local cache for a project."""
        local_dir = _local_path(user_id, project_id)
        if local_dir.exists():
            shutil.rmtree(str(local_dir), ignore_errors=True)
            log.info(f"Cleaned up local cache for {user_id}/{project_id}")

    async def start_periodic_sync(self, user_id: str, project_id: str,
                                   interval: int = 600) -> None:
        """Start periodic background sync (every `interval` seconds)."""
        task_key = f"{user_id}/{project_id}"
        if task_key in self._periodic_tasks:
            log.warning(f"Periodic sync already running for {task_key}")
            return

        async def _sync_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await self.backup(user_id, project_id)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.warning(f"Periodic sync error for {task_key}: {e}")

        task = asyncio.create_task(_sync_loop())
        self._periodic_tasks[task_key] = task
        log.info(f"Started periodic sync for {task_key} every {interval}s")

    async def stop_periodic_sync(self, user_id: str, project_id: str) -> None:
        """Stop periodic sync."""
        task_key = f"{user_id}/{project_id}"
        task = self._periodic_tasks.pop(task_key, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            log.info(f"Stopped periodic sync for {task_key}")
