import uuid

from clipforge.common import logging as logging_mod
from clipforge.processing.domain.entities import Job
from clipforge.processing.domain.ports import JobRepository

logger = logging_mod.get_logger(__name__)

ACTIVE_STATUSES = ("pending", "running")


class JobTracker:
    """Idempotent job lifecycle manager.

    Each pipeline stage maps to exactly one row in `jobs`, keyed by a stable
    dedupe key (`{video_id}:{stage}`). Redelivered messages cannot start a
    stage twice, which prevents duplicate clips/analysis from broker retries.
    """

    def __init__(self, jobs: JobRepository) -> None:
        self._jobs = jobs

    async def begin(
        self,
        video_id: uuid.UUID,
        job_type: str,
        dedupe_key: str,
        max_attempts: int = 5,
    ) -> Job | None:
        existing = await self._jobs.get_by_dedupe_key(dedupe_key)
        if existing is not None and existing.status in ACTIVE_STATUSES + ("succeeded",):
            logger.info(
                "job already handled; skipping",
                job_id=str(existing.id),
                job_type=job_type,
                video_id=str(video_id),
                status=existing.status,
            )
            return None
        if existing is None:
            return await self._jobs.create(
                Job(
                    video_id=video_id,
                    type=job_type,
                    status="running",
                    attempts=1,
                    max_attempts=max_attempts,
                    dedupe_key=dedupe_key,
                )
            )
        return await self._jobs.mark_running(existing.id)

    async def succeed(self, job_id: uuid.UUID) -> None:
        await self._jobs.mark_succeeded(job_id)

    async def fail(self, job_id: uuid.UUID, error: str) -> None:
        await self._jobs.mark_failed(job_id, error[:2000])
