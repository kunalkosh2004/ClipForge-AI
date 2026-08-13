import uuid

from clipforge.analysis.domain.presets import format_for_preset
from clipforge.clips.domain.entities import Clip
from clipforge.clips.domain.ports import ClipRepository
from clipforge.common import logging as logging_mod
from clipforge.common.errors import EntityNotFoundError
from clipforge.common.pagination import PageRequest, PageResult
from clipforge.common.ports import StorageProvider
from clipforge.common.times import clip_time
from clipforge.processing.domain.ports import StatusNotifier

logger = logging_mod.get_logger(__name__)


class ClipService:
    def __init__(
        self,
        clips: ClipRepository,
        storage: StorageProvider,
        notifier: StatusNotifier,
    ) -> None:
        self._clips = clips
        self._storage = storage
        self._notifier = notifier

    async def create_clips_from_editing_plan(
        self,
        video_id: uuid.UUID,
        project_id: uuid.UUID,
        editing_plan: dict,
    ) -> list[Clip]:
        existing_count = await self._clips.count_for_video(video_id)
        if existing_count > 0:
            logger.info(
                "clips already created; reusing existing",
                video_id=str(video_id),
                clip_count=existing_count,
            )
            page = await self._clips.list_for_video(video_id, PageRequest(limit=500))
            return list(page.items)

        clips_data = editing_plan.get("clips", [])
        clip_format = format_for_preset(editing_plan.get("preset"))
        created: list[Clip] = []
        for clip_data in clips_data:
            start = clip_time(clip_data, "start_time", "start")
            end = clip_time(clip_data, "end_time", "end")
            title = (
                clip_data.get("hook")
                or clip_data.get("why_it_is_engaging")
                or f"Clip at {start:.1f}s"
            )
            clip = Clip(
                video_id=video_id,
                project_id=project_id,
                title=title,
                start_seconds=start,
                end_seconds=end,
                duration_seconds=max(end - start, 0.0),
                editing_plan_json=clip_data,
                format=clip_format,
                status="pending",
            )
            clip = await self._clips.create(clip)
            created.append(clip)
        return created

    async def list_clips_for_video(
        self, video_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        return await self._clips.list_for_video(video_id, page)

    async def list_clips_for_project(
        self, project_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        return await self._clips.list_for_project(project_id, page)

    async def get_clip(self, clip_id: uuid.UUID) -> Clip:
        clip = await self._clips.get_by_id(clip_id)
        if clip is None:
            raise EntityNotFoundError("clip not found")
        return clip

    async def get_clip_download_url(self, clip_id: uuid.UUID) -> str:
        clip = await self.get_clip(clip_id)
        # Prefer rendered version with captions, fall back to raw cut
        storage_key = clip.render_storage_key or clip.storage_key
        if storage_key is None:
            raise EntityNotFoundError("clip not ready for download")
        return await self._storage.signed_download_url(storage_key, expires_in=3600)

    async def mark_cutting(self, clip_id: uuid.UUID) -> Clip | None:
        return await self._clips.update_status(clip_id, "cutting")

    async def mark_ready(
        self, clip_id: uuid.UUID, storage_key: str, thumbnail_storage_key: str | None = None
    ) -> Clip | None:
        return await self._clips.update_storage(
            clip_id, storage_key, thumbnail_storage_key=thumbnail_storage_key
        )

    async def mark_failed(self, clip_id: uuid.UUID) -> Clip | None:
        return await self._clips.update_status(clip_id, "failed")

    async def delete_clip(self, clip_id: uuid.UUID) -> None:
        await self.get_clip(clip_id)
        await self._clips.delete(clip_id)
