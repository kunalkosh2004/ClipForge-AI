import uuid
from abc import ABC, abstractmethod
from typing import Any

from clipforge.common.pagination import PageRequest, PageResult
from clipforge.videos.domain.entities import Project, Video


class ProjectRepository(ABC):
    @abstractmethod
    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        """Return the project or None."""

    @abstractmethod
    async def create(self, project: Project) -> Project:
        """Persist a project and return it with generated fields populated."""

    @abstractmethod
    async def list_for_owner(
        self, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Project]:
        """Return projects owned by this user, newest first, with pagination."""

    @abstractmethod
    async def delete(self, project_id: uuid.UUID) -> bool:
        """Delete a project by id. Returns True if deleted."""


class VideoRepository(ABC):
    @abstractmethod
    async def get_owned(self, video_id: uuid.UUID, owner_id: uuid.UUID) -> Video | None:
        """Return a video only when it belongs to a project owned by owner_id."""

    @abstractmethod
    async def get_by_id(self, video_id: uuid.UUID) -> Video | None:
        """Return the video or None."""

    @abstractmethod
    async def create(self, video: Video) -> Video:
        """Persist a video and return it with generated fields populated."""

    @abstractmethod
    async def update_status(self, video_id: uuid.UUID, status: str) -> Video | None:
        """Transition the video status. Returns the updated video or None."""

    @abstractmethod
    async def update_editing_style(
        self, video_id: uuid.UUID, editing_style: str | None
    ) -> Video | None:
        """Set the per-video editing prompt. Returns the updated video or None."""

    @abstractmethod
    async def update_metadata(
        self,
        video_id: uuid.UUID,
        *,
        checksum: str,
        size_bytes: int,
        duration_seconds: float | None,
        metadata_json: dict[str, Any],
        status: str,
    ) -> Video | None:
        """Update video metadata fields after extraction. Returns the updated video or None."""

    @abstractmethod
    async def update_imported(
        self,
        video_id: uuid.UUID,
        *,
        original_filename: str,
        checksum: str,
        size_bytes: int,
        duration_seconds: float | None,
        metadata_json: dict[str, Any],
        status: str,
    ) -> Video | None:
        """Populate a video imported from an external source after download.

        Returns the updated video or None.
        """

    @abstractmethod
    async def list_for_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Video]:
        """Return videos in a project with ownership check and pagination."""

    @abstractmethod
    async def delete(self, video_id: uuid.UUID) -> bool:
        """Delete a video by id. Returns True if deleted."""
