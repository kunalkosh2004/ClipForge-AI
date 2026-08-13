import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.common.errors import EntityNotFoundError, ForbiddenError, UserError
from clipforge.common.events import EVENT_VIDEO_IMPORT_QUEUED, EVENT_VIDEO_UPLOADED, DomainEvent
from clipforge.common.ids import uuid7
from clipforge.common.pagination import PageRequest, PageResult
from clipforge.common.ports import QueueBroker, StorageProvider
from clipforge.common.ports.event_bus import EventBus
from clipforge.videos.application.schemas import (
    CompleteUploadResponse,
    CreateVideoRequest,
    ImportVideoRequest,
    ImportVideoResponse,
    StartUploadResponse,
    VideoResponse,
)
from clipforge.videos.domain.entities import Project, Video
from clipforge.videos.domain.ports import ProjectRepository, VideoRepository
from clipforge.videos.infrastructure.youtube import extract_youtube_id

SIGNED_URL_TTL_SECONDS = 3600

logger = logging_mod.get_logger(__name__)


class VideoService:
    def __init__(
        self,
        projects: ProjectRepository,
        videos: VideoRepository,
        storage: StorageProvider,
        queue: QueueBroker,
        events: EventBus,
        media_queue: str,
        default_queue: str = "default",
    ) -> None:
        self._projects = projects
        self._videos = videos
        self._storage = storage
        self._queue = queue
        self._events = events
        self._media_queue = media_queue
        self._default_queue = default_queue

    async def create_project(self, owner_id: uuid.UUID, name: str) -> Project:
        return await self._projects.create(Project(owner_id=owner_id, name=name.strip()))

    async def list_projects(
        self, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Project]:
        return await self._projects.list_for_owner(owner_id, page)

    async def delete_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        project = await self._projects.get_by_id(project_id)
        if project is None:
            raise EntityNotFoundError("project not found")
        if project.owner_id != owner_id:
            raise ForbiddenError("not your project")
        await self._projects.delete(project_id)

    async def list_videos(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Video]:
        project = await self._projects.get_by_id(project_id)
        if project is None:
            raise EntityNotFoundError("project not found")
        if project.owner_id != owner_id:
            raise ForbiddenError("not your project")
        return await self._videos.list_for_project(project_id, owner_id, page)

    async def start_upload(
        self, owner_id: uuid.UUID, request: CreateVideoRequest
    ) -> StartUploadResponse:
        project = await self._projects.get_by_id(request.project_id)
        if project is None:
            raise EntityNotFoundError("project not found")
        if project.owner_id != owner_id:
            raise ForbiddenError("not your project")
        if not request.content_type.startswith("video/"):
            raise UserError("content_type must be a video mime type")

        filename = Path(request.filename).name
        video_id = uuid7()
        storage_key = f"videos/{video_id}/{filename}"
        video = await self._videos.create(
            Video(
                id=video_id,
                project_id=project.id,
                original_filename=filename,
                storage_key=storage_key,
                content_type=request.content_type,
                size_bytes=request.size_bytes,
                status="uploading",
            )
        )
        upload_url = await self._storage.signed_upload_url(
            storage_key, request.content_type, expires_in=SIGNED_URL_TTL_SECONDS
        )
        return StartUploadResponse(
            video_id=video.id,
            storage_key=storage_key,
            upload_url=upload_url,
            expires_in=SIGNED_URL_TTL_SECONDS,
        )

    async def complete_upload(
        self, owner_id: uuid.UUID, video_id: uuid.UUID
    ) -> CompleteUploadResponse:
        """Finalize an upload: the object is now stored, but nothing is
        processed yet. Processing starts explicitly via `process_video`."""
        video = await self._videos.get_owned(video_id, owner_id)
        if video is None:
            raise EntityNotFoundError("video not found")
        if video.status != "uploading":
            raise UserError("upload is not in progress")
        if not await self._storage.exists(video.storage_key):
            raise UserError("uploaded object is missing from storage")

        updated = await self._videos.update_status(video.id, status="uploaded")
        if updated is None:
            raise EntityNotFoundError("video not found")
        video = updated
        await self._emit(EVENT_VIDEO_UPLOADED, video.id, {"filename": video.original_filename})
        return CompleteUploadResponse(video_id=video.id, status=video.status)

    async def import_from_youtube(
        self, owner_id: uuid.UUID, request: ImportVideoRequest
    ) -> ImportVideoResponse:
        project = await self._projects.get_by_id(request.project_id)
        if project is None:
            raise EntityNotFoundError("project not found")
        if project.owner_id != owner_id:
            raise ForbiddenError("not your project")

        youtube_id = extract_youtube_id(request.url)
        if youtube_id is None:
            raise UserError("not a valid YouTube URL")

        video_id = uuid7()
        filename = f"{youtube_id}.mp4"
        video = await self._videos.create(
            Video(
                id=video_id,
                project_id=project.id,
                original_filename=request.title or f"YouTube {youtube_id}",
                source_url=request.url.strip(),
                storage_key=f"videos/{video_id}/{filename}",
                content_type="video/mp4",
                size_bytes=0,
                status="importing",
            )
        )
        self._queue.enqueue(
            "youtube_import",
            {"video_id": str(video.id), "url": request.url.strip()},
            queue="import",
        )
        await self._emit(EVENT_VIDEO_IMPORT_QUEUED, video.id, {"url": request.url.strip()})
        return ImportVideoResponse(video_id=video.id, status=video.status)

    async def get_video(self, owner_id: uuid.UUID, video_id: uuid.UUID) -> VideoResponse:
        video = await self._videos.get_owned(video_id, owner_id)
        if video is None:
            raise EntityNotFoundError("video not found")
        return _video_response(video)

    async def update_video(
        self, owner_id: uuid.UUID, video_id: uuid.UUID, editing_style: str | None
    ) -> VideoResponse:
        """Set the video's editing prompt (optional, per-video)."""
        video = await self._videos.get_owned(video_id, owner_id)
        if video is None:
            raise EntityNotFoundError("video not found")
        updated = await self._videos.update_editing_style(
            video.id, (editing_style or "").strip() or None
        )
        if updated is None:
            raise EntityNotFoundError("video not found")
        return _video_response(updated)

    async def process_video(self, owner_id: uuid.UUID, video_id: uuid.UUID) -> None:
        """Start full processing on demand: the stored video runs the legacy
        pipeline (metadata -> AI analysis -> clip extraction -> render) plus
        the artifact intelligence workflow that drives emphasis timing."""
        video = await self._videos.get_owned(video_id, owner_id)
        if video is None:
            raise EntityNotFoundError("video not found")
        if video.status in ("uploading", "importing", "processing", "analyzing"):
            raise UserError("video is not ready to be processed")
        if not await self._storage.exists(video.storage_key):
            raise UserError("video object is missing from storage")

        updated = await self._videos.update_status(video.id, status="processing")
        if updated is None:
            raise EntityNotFoundError("video not found")
        video = updated
        self._queue.enqueue(
            "metadata_extraction",
            {"video_id": str(video.id), "storage_key": video.storage_key},
            queue=self._default_queue,
        )
        self._queue.enqueue(
            "start_intelligence",
            {"video_id": str(video.id)},
            queue=self._media_queue,
        )

    async def start_intelligence(
        self, owner_id: uuid.UUID, video_id: uuid.UUID
    ) -> None:
        """Enqueue the artifact pipeline for a video (idempotent: the workflow
        engine only creates missing DAG nodes)."""
        video = await self._videos.get_owned(video_id, owner_id)
        if video is None:
            raise EntityNotFoundError("video not found")
        self._queue.enqueue(
            "start_intelligence",
            {"video_id": str(video.id)},
            queue=self._media_queue,
        )

    async def delete_video(self, owner_id: uuid.UUID, video_id: uuid.UUID) -> None:
        video = await self._videos.get_owned(video_id, owner_id)
        if video is None:
            raise EntityNotFoundError("video not found")
        await self._videos.delete(video_id)

    async def _emit(self, event_type: str, video_id: uuid.UUID, payload: dict[str, Any]) -> None:
        try:
            await self._events.publish(
                DomainEvent(type=event_type, aggregate_id=str(video_id), payload=payload)
            )
        except Exception:
            logger.exception("event publish failed", event_type=event_type, video_id=str(video_id))


def _video_response(video: Video) -> VideoResponse:
    return VideoResponse(
        id=video.id,
        project_id=video.project_id,
        original_filename=video.original_filename,
        source_url=video.source_url,
        storage_key=video.storage_key,
        content_type=video.content_type,
        size_bytes=video.size_bytes,
        checksum=video.checksum,
        duration_seconds=video.duration_seconds,
        editing_style=video.editing_style,
        status=video.status,
        created_at=video.created_at or datetime.now(UTC),
    )
