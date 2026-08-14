import uuid
from abc import ABC, abstractmethod

from clipforge.clips.domain.entities import Clip
from clipforge.common.pagination import PageRequest, PageResult


class ClipRepository(ABC):
    @abstractmethod
    async def get_by_id(self, clip_id: uuid.UUID) -> Clip | None:
        """Return the clip or None."""

    @abstractmethod
    async def list_for_video(
        self, video_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        """Return clips for a video, ordered by start time, with pagination."""

    @abstractmethod
    async def list_for_project(
        self, project_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        """Return clips for a project with pagination."""

    @abstractmethod
    async def create(self, clip: Clip) -> Clip:
        """Persist a clip and return it with generated fields populated."""

    @abstractmethod
    async def count_for_video(self, video_id: uuid.UUID) -> int:
        """Return the number of clips already created for a video."""

    @abstractmethod
    async def update_status(self, clip_id: uuid.UUID, status: str) -> Clip | None:
        """Transition the clip status. Returns the updated clip or None."""

    @abstractmethod
    async def update_storage(
        self, clip_id: uuid.UUID, storage_key: str, thumbnail_storage_key: str | None = None
    ) -> Clip | None:
        """Update the storage key after cutting. Returns the updated clip or None."""

    @abstractmethod
    async def update_render(
        self,
        clip_id: uuid.UUID,
        render_storage_key: str,
        thumbnail_storage_key: str | None = None,
    ) -> Clip | None:
        """Update the render storage key after caption rendering.

        Returns the updated clip or None.
        """

    @abstractmethod
    async def delete(self, clip_id: uuid.UUID) -> bool:
        """Delete a clip by id. Returns True if deleted."""


class VideoCutter(ABC):
    @abstractmethod
    async def cut_clip(
        self,
        source_path: str,
        start_seconds: float,
        end_seconds: float,
        output_path: str,
    ) -> None:
        """Extract a clip from the source video using FFmpeg."""


class ThumbnailGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        source_path: str,
        timestamp_seconds: float,
        output_path: str,
        width: int = 1080,
        height: int = 1920,
    ) -> None:
        """Extract a thumbnail frame from the source video at the given timestamp."""
