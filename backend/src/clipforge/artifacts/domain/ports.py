import uuid
from abc import ABC, abstractmethod
from typing import Any

from clipforge.artifacts.domain.entities import Artifact


class ArtifactStore(ABC):
    """Blob persistence for artifacts (the JSON documents themselves)."""

    @abstractmethod
    async def write(
        self,
        video_id: uuid.UUID,
        kind: str,
        payload: dict[str, Any],
        version: str,
    ) -> Artifact:
        """Persist an artifact document and return its metadata index."""

    @abstractmethod
    async def read_payload(self, video_id: uuid.UUID, kind: str) -> dict[str, Any] | None:
        """Read the latest payload for a (video, kind), or None if absent."""

    @abstractmethod
    async def exists(self, video_id: uuid.UUID, kind: str) -> bool:
        """True when a blob exists for (video, kind)."""


class ArtifactRepository(ABC):
    """Database index of latest artifacts per (video, kind)."""

    @abstractmethod
    async def create(self, artifact: Artifact) -> Artifact:
        ...

    @abstractmethod
    async def get_latest(self, video_id: uuid.UUID, kind: str) -> Artifact | None:
        ...

    @abstractmethod
    async def list_for_video(self, video_id: uuid.UUID) -> list[Artifact]:
        ...

    @abstractmethod
    async def delete_for_video(self, video_id: uuid.UUID) -> int:
        ...
