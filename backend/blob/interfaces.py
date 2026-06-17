"""IBlobStorage interface — abstract contract for blob storage backends."""
from abc import ABC, abstractmethod


class IBlobStorage(ABC):

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    async def download(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    async def get_metadata(self, key: str) -> dict: ...

    @abstractmethod
    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str: ...
