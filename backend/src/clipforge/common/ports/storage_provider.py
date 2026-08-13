from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageProvider(ABC):
    @abstractmethod
    async def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        """Persist a blob at key, overwriting any existing content."""

    @abstractmethod
    async def get(self, key: str) -> BinaryIO:
        """Open a readable stream for key. Raises if the object is missing."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove key. No-op if it does not exist."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True when an object exists at key."""

    @abstractmethod
    async def signed_upload_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        """Return a time-limited URL a client can PUT to, bypassing the API."""

    @abstractmethod
    async def signed_download_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a time-limited URL for fetching the object."""
