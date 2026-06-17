"""GCS Blob storage implementation — mirrors the IBlobStorage interface."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial

from google.cloud import storage as gcs

from blob.interfaces import IBlobStorage
from core.log import create_logger

log = create_logger("blob.gcs")


class GCSBlobStorage(IBlobStorage):

    def __init__(self, bucket_name: str):
        self._client = gcs.Client()
        self._bucket = self._client.bucket(bucket_name)
        self._executor = ThreadPoolExecutor(max_workers=4)

    def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self._executor, partial(fn, *args, **kwargs))

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        blob = self._bucket.blob(key)
        await self._run(blob.upload_from_string, data, content_type=content_type)

    async def download(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        return await self._run(blob.download_as_bytes)

    async def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        try:
            await self._run(blob.delete)
        except Exception:
            pass

    async def exists(self, key: str) -> bool:
        blob = self._bucket.blob(key)
        return await self._run(blob.exists)

    async def list_keys(self, prefix: str = "") -> list[str]:
        def _list():
            return [b.name for b in self._client.list_blobs(self._bucket, prefix=prefix)]
        return await self._run(_list)

    async def get_metadata(self, key: str) -> dict:
        blob = self._bucket.blob(key)
        await self._run(blob.reload)
        return {
            "size": blob.size,
            "content_type": blob.content_type,
            "updated": blob.updated.isoformat() if blob.updated else None,
            "md5_hash": blob.md5_hash,
        }

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        blob = self._bucket.blob(key)
        return blob.generate_signed_url(expiration=timedelta(seconds=expires_in))
