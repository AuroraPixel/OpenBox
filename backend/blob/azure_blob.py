"""Azure Blob Storage implementation of IBlobStorage."""
from typing import AsyncIterator

from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from core.log import create_logger

log = create_logger("blob.azure")


class AzureBlobStorage:
    def __init__(self, connection_string: str, container_name: str = "ads-staging"):
        self._connection_string = connection_string
        self._container_name = container_name
        self._service_client: BlobServiceClient | None = None
        self._container_client: ContainerClient | None = None

    async def _ensure_client(self) -> ContainerClient:
        if self._container_client is None:
            self._service_client = BlobServiceClient.from_connection_string(self._connection_string)
            self._container_client = self._service_client.get_container_client(self._container_name)
            try:
                await self._container_client.create_container()
            except Exception:
                pass  # Container already exists
            log.info(f"Azure Blob connected: container={self._container_name}")
        return self._container_client

    async def upload(self, key: str, data: bytes | AsyncIterator[bytes],
                     metadata: dict | None = None) -> str:
        client = await self._ensure_client()
        blob_client = client.get_blob_client(key)
        await blob_client.upload_blob(data, overwrite=True, metadata=metadata)
        return key

    async def download(self, key: str) -> AsyncIterator[bytes]:
        client = await self._ensure_client()
        blob_client = client.get_blob_client(key)
        stream = await blob_client.download_blob()
        async for chunk in stream.chunks():
            yield chunk

    async def delete(self, key: str) -> None:
        client = await self._ensure_client()
        blob_client = client.get_blob_client(key)
        try:
            await blob_client.delete_blob()
        except Exception:
            pass  # Blob doesn't exist

    async def exists(self, key: str) -> bool:
        client = await self._ensure_client()
        blob_client = client.get_blob_client(key)
        try:
            await blob_client.get_blob_properties()
            return True
        except Exception:
            return False

    async def list_keys(self, prefix: str) -> list[str]:
        client = await self._ensure_client()
        keys = []
        async for blob in client.list_blobs(name_starts_with=prefix):
            keys.append(blob.name)
        return keys

    async def get_metadata(self, key: str) -> dict | None:
        client = await self._ensure_client()
        blob_client = client.get_blob_client(key)
        try:
            props = await blob_client.get_blob_properties()
            return props.metadata
        except Exception:
            return None

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        from datetime import datetime, timedelta, timezone
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        client = await self._ensure_client()
        blob_client = client.get_blob_client(key)
        # Extract account details from connection string
        account_name = self._service_client.account_name
        account_key = self._service_client.credential.account_key
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self._container_name,
            blob_name=key,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expires),
        )
        return f"{blob_client.url}?{sas_token}"

    async def close(self) -> None:
        if self._service_client:
            await self._service_client.close()
            self._service_client = None
            self._container_client = None
            log.info("Azure Blob connection closed")
