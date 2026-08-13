import uuid
from typing import Any

from clipforge.admin.infrastructure.dead_letters import RedisDeadLetterStore
from clipforge.common import logging as logging_mod
from clipforge.common.errors import EntityNotFoundError
from clipforge.common.pagination import PageRequest, PageResult
from clipforge.common.ports import QueueBroker
from clipforge.config import get_settings
from clipforge.processing.domain.entities import Job
from clipforge.processing.domain.ports import JobRepository
from clipforge.videos.domain.ports import VideoRepository

logger = logging_mod.get_logger(__name__)

JOB_TYPE_TO_TASK = {
    "metadata_extraction": "metadata_extraction",
    "ai_analysis": "ai_analysis",
    "clip_extraction": "clip_extraction",
    "render": "render",
}


def _job_queue(job_type: str) -> str:
    settings = get_settings()
    return {
        "metadata_extraction": settings.queue_default,
        "ai_analysis": settings.queue_ai,
        "clip_extraction": settings.queue_default,
        "render": settings.queue_render,
    }.get(job_type, settings.queue_default)


class AdminService:
    def __init__(
        self,
        jobs: JobRepository,
        videos: VideoRepository,
        queue: QueueBroker,
        dead_letters: RedisDeadLetterStore,
    ) -> None:
        self._jobs = jobs
        self._videos = videos
        self._queue = queue
        self._dead_letters = dead_letters

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        video_id: uuid.UUID | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Job]:
        return await self._jobs.list_all(
            status=status, job_type=job_type, video_id=video_id, page=page
        )

    async def retry_job(self, job_id: uuid.UUID) -> Job:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise EntityNotFoundError("job not found")
        task_name = JOB_TYPE_TO_TASK.get(job.type)
        if task_name is None:
            raise EntityNotFoundError(f"no retry path for job type {job.type}")

        payload: dict[str, Any] = {"video_id": str(job.video_id)}
        if job.type == "metadata_extraction":
            video = await self._videos.get_by_id(job.video_id)
            if video is None:
                raise EntityNotFoundError("video not found")
            payload["storage_key"] = video.storage_key

        # Reset a previously finished job so the pipeline's dedupe check
        # (JobTracker.begin) re-runs the stage instead of skipping it.
        await self._jobs.mark_failed(job.id, "retry requested")

        self._queue.enqueue(task_name, payload, queue=_job_queue(job.type))
        logger.info("job_retried", job_id=str(job_id), task=task_name, video_id=str(job.video_id))
        return job

    async def list_dead_letters(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._dead_letters.list(limit=limit)

    async def retry_dead_letter(self, entry_id: str) -> dict[str, Any]:
        entry = await self._dead_letters.get(entry_id)
        if entry is None:
            raise EntityNotFoundError("dead letter not found")
        actor_name = entry["actor_name"]
        payload = entry["payload"]
        queue = entry.get("queue") or "default"
        self._queue.enqueue(actor_name, payload, queue=queue)
        await self._dead_letters.remove(entry_id)
        logger.info(
            "dead_letter_retried",
            entry_id=entry_id,
            actor=actor_name,
            video_id=payload.get("video_id"),
        )
        return entry
