from abc import ABC, abstractmethod


class CacheProvider(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the cached value or None."""

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Cache value, optionally expiring after ttl_seconds."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove key. No-op when absent."""
