import asyncio
import uuid
from datetime import UTC, datetime

from clipforge.common import logging as logging_mod
from clipforge.common.ports import StorageProvider
from clipforge.processing.domain.entities import Job
from clipforge.processing.domain.ports import JobRepository, StatusNotifier
from clipforge.processing.infrastructure.audio_analysis import analyze_audio_energy
from clipforge.processing.infrastructure.ffprobe import (
    build_metadata,
    download_to_tempfile,
    run_ffprobe,
)
from clipforge.videos.domain.ports import VideoRepository

logger = logging_mod.get_logger(__name__)

JOB_TYPE_METADATA = "metadata_extraction"
VIDEO_STATUS_PROCESSING = "processing"
VIDEO_STATUS_FAILED = "failed"

STATUS_CHANNEL = "clipforge:status"


class MetadataExtractionService:
    def __init__(
        self,
        videos: VideoRepository,
        jobs: JobRepository,
        storage: StorageProvider,
        notifier: StatusNotifier,
    ) -> None:
        self._videos = videos
        self._jobs = jobs
        self._storage = storage
        self._notifier = notifier

    async def begin(self, video_id: uuid.UUID, storage_key: str) -> Job | None:
        dedupe_key = f"{video_id}:{JOB_TYPE_METADATA}"
        existing = await self._jobs.get_by_dedupe_key(dedupe_key)
        if existing is not None and existing.status in ("running", "succeeded"):
            logger.info("job already handled; skipping", job_id=str(existing.id))
            return None

        video = await self._videos.get_by_id(video_id)
        if video is None:
            logger.warning("video not found; dropping job", video_id=str(video_id))
            return None

        if existing is None:
            job = await self._jobs.create(
                Job(
                    video_id=video_id,
                    type=JOB_TYPE_METADATA,
                    status="running",
                    attempts=1,
                    max_attempts=3,
                    dedupe_key=dedupe_key,
                )
            )
        else:
            job = await self._jobs.mark_running(existing.id)
        await self._notify(video_id, "processing", JOB_TYPE_METADATA)
        return job

    async def extract(self, job: Job) -> None:
        video = await self._videos.get_by_id(job.video_id)
        if video is None:
            raise RuntimeError(f"video {job.video_id} vanished before extraction")

        path, checksum, size_bytes = await download_to_tempfile(self._storage, video.storage_key)
        try:
            probe = await asyncio.to_thread(run_ffprobe, path)
            metadata = build_metadata(probe)
            duration = metadata["format"].get("duration")

            # Beat-drop / energy analysis drives timed effects in rendering
            # (punch zooms, transitions, SFX, music). Best-effort: never fails
            # the stage when the track is silent or undecodable.
            try:
                audio = await asyncio.to_thread(analyze_audio_energy, path)
            except Exception:
                logger.exception("audio_analysis_failed", video_id=str(video.id))
                from clipforge.processing.infrastructure.audio_analysis import (
                    _empty_profile,
                )

                audio = _empty_profile()
            metadata.setdefault("audio", {}).update(audio)

            await self._videos.update_metadata(
                video.id,
                checksum=checksum,
                size_bytes=size_bytes,
                duration_seconds=duration,
                metadata_json=metadata,
                status=VIDEO_STATUS_PROCESSING,
            )
        finally:
            path.unlink(missing_ok=True)

    async def succeed(self, job_id: uuid.UUID, video_id: uuid.UUID) -> None:
        await self._jobs.mark_succeeded(job_id)
        await self._notify(video_id, VIDEO_STATUS_PROCESSING, JOB_TYPE_METADATA)

    async def fail(self, job_id: uuid.UUID, video_id: uuid.UUID, error: str) -> None:
        await self._jobs.mark_failed(job_id, error[:2000])
        await self._videos.update_status(video_id, VIDEO_STATUS_FAILED)
        await self._notify(video_id, VIDEO_STATUS_FAILED, JOB_TYPE_METADATA)

    async def _notify(self, video_id: uuid.UUID, status: str, stage: str) -> None:
        try:
            await self._notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": status,
                    "stage": stage,
                    "ts": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            logger.warning("status publish failed; continuing", video_id=str(video_id))
