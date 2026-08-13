import asyncio
import shutil
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from clipforge.admin.infrastructure.dead_letters import RedisDeadLetterStore
from clipforge.analysis.application.service import AnalysisService
from clipforge.analysis.infrastructure.repositories import (
    SQLAlchemyAnalysisResultRepository,
    SQLAlchemyTranscriptRepository,
)
from clipforge.artifacts.infrastructure.repositories import SQLAlchemyArtifactRepository
from clipforge.artifacts.infrastructure.storage_store import StorageArtifactStore
from clipforge.clips.application.service import ClipService
from clipforge.clips.infrastructure.ffmpeg_cutter import FFmpegCutter
from clipforge.clips.infrastructure.repositories import SQLAlchemyClipRepository
from clipforge.clips.infrastructure.thumbnail import FFmpegThumbnailGenerator
from clipforge.common import logging as logging_mod
from clipforge.common.events import (
    EVENT_JOB_DEAD_LETTERED,
    EVENT_VIDEO_ANALYZED,
    EVENT_VIDEO_CLIPS_CREATED,
    EVENT_VIDEO_CLIPS_RENDERED,
    EVENT_VIDEO_FAILED,
    EVENT_VIDEO_IMPORTED,
    EVENT_VIDEO_METADATA_EXTRACTED,
    EVENT_VIDEO_READY,
    DomainEvent,
)
from clipforge.common.observability import (
    record_job_completion,
    setup_metrics,
    setup_tracing,
    trace_id_from_context,
)
from clipforge.config import get_settings
from clipforge.container import build_container
from clipforge.db.session import SessionLocal
from clipforge.processing.application.jobs import JobTracker
from clipforge.processing.application.service import MetadataExtractionService
from clipforge.processing.infrastructure.ffprobe import (
    build_metadata,
    download_to_tempfile,
    run_ffprobe,
    sha256_file,
)
from clipforge.processing.infrastructure.repositories import SQLAlchemyJobRepository
from clipforge.processing.infrastructure.status import RedisStatusNotifier
from clipforge.rendering.application.service import RenderingService
from clipforge.rendering.infrastructure.ffmpeg_renderer import FFmpegCaptionRenderer
from clipforge.rendering.infrastructure.framing_analyzer import OpenCVFramingAnalyzer
from clipforge.videos.infrastructure.repositories import SQLAlchemyVideoRepository
from clipforge.videos.infrastructure.youtube import YouTubeDownloader

logger = logging_mod.get_logger(__name__)

settings = get_settings()
logging_mod.configure_logging(settings.app_env, settings.log_level)
setup_metrics()
tracer = setup_tracing("clipforge-worker", settings.otel_enabled)

QUEUE_DEFAULT = settings.queue_default
QUEUE_IMPORT = settings.queue_import
QUEUE_AI = settings.queue_ai
QUEUE_RENDER = settings.queue_render
QUEUE_DEAD = settings.queue_dead

broker: dramatiq.Broker = RedisBroker(url=settings.redis_url)  # type: ignore[no-untyped-call]
dramatiq.set_broker(broker)

_container = build_container(settings)


def task(
    queue: str = QUEUE_DEFAULT,
    *,
    max_retries: int = 5,
    min_backoff: int = 1000,
    max_backoff: int = 60_000,
    on_retry_exhausted: str | None = "dead_letter",
    time_limit: int | None = None,
) -> Callable[[Callable[..., Any]], dramatiq.Actor]:
    """Declare a pipeline actor with a sane retry/backoff policy.

    Policy reasoning:
    - Retries use exponential backoff (2x, from 1s up to 60s) so transient
      failures (db/redis/network) recover without hammering the system.
    - After `max_retries` the message is routed to the `dead_letter` actor
      (via dramatiq's `on_retry_exhausted`), which persists it for admin
      inspection and marks the video failed.
    - `time_limit` (milliseconds) overrides dramatiq's 10-minute default
      for long-running stages (e.g. AI analysis uploads + Gemini calls).
      Only set when provided so the broker default applies otherwise.
    """

    def deco(fn: Callable[..., Any]) -> dramatiq.Actor:
        options: dict[str, Any] = dict(
            queue_name=queue,
            max_retries=max_retries,
            min_backoff=min_backoff,
            max_backoff=max_backoff,
            on_retry_exhausted=on_retry_exhausted,
        )
        if time_limit is not None:
            options["time_limit"] = time_limit
        return dramatiq.actor(fn, **options)

    return deco


# ---------------------------------------------------------------------------
# metadata_extraction
# ---------------------------------------------------------------------------


@task(queue=QUEUE_DEFAULT, max_retries=5, max_backoff=60_000)
def metadata_extraction(payload: dict[str, Any]) -> None:
    asyncio.run(_run_metadata_extraction(payload))


async def _run_metadata_extraction(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    storage_key = str(payload["storage_key"])
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span("pipeline.metadata_extraction") as span:
            span.set_attribute("video_id", str(video_id))
            with logging_mod.request_context(
                video_id=str(video_id),
                stage="metadata_extraction",
                trace_id=trace_id_from_context() or "none",
            ):
                await _execute_metadata_extraction(video_id, storage_key)
        record_job_completion("metadata_extraction", "succeeded", time.perf_counter() - started)
    except Exception:
        record_job_completion("metadata_extraction", "failed", time.perf_counter() - started)
        raise


async def _execute_metadata_extraction(video_id: uuid.UUID, storage_key: str) -> None:
    async with SessionLocal() as session:
        notifier = RedisStatusNotifier(settings.redis_url)
        service = MetadataExtractionService(
            videos=SQLAlchemyVideoRepository(session),
            jobs=SQLAlchemyJobRepository(session),
            storage=_container.storage,
            notifier=notifier,
        )
        job = await service.begin(video_id, storage_key)
        if job is None:
            await session.commit()
            return

        try:
            await service.extract(job)
        except Exception as exc:
            logger.exception("metadata_extraction_failed", video_id=str(video_id))
            await service.fail(job.id, video_id, str(exc))
            await session.commit()
            await _emit(EVENT_VIDEO_FAILED, video_id, _failure_payload("metadata_extraction", exc))
            raise

        await service.succeed(job.id, video_id)
        await session.commit()
        await _emit(EVENT_VIDEO_METADATA_EXTRACTED, video_id, {})
        logger.info("metadata_extraction_complete", video_id=str(video_id))

    _enqueue("ai_analysis", {"video_id": str(video_id)}, queue=QUEUE_AI)


# ---------------------------------------------------------------------------
# ai_analysis
# ---------------------------------------------------------------------------


@task(queue=QUEUE_AI, max_retries=5, max_backoff=60_000, time_limit=2_700_000)
def ai_analysis(payload: dict[str, Any]) -> None:
    asyncio.run(_run_ai_analysis(payload))


async def _run_ai_analysis(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span("pipeline.ai_analysis") as span:
            span.set_attribute("video_id", str(video_id))
            with logging_mod.request_context(
                video_id=str(video_id),
                stage="ai_analysis",
                trace_id=trace_id_from_context() or "none",
            ):
                await _execute_ai_analysis(video_id)
        record_job_completion("ai_analysis", "succeeded", time.perf_counter() - started)
    except Exception:
        record_job_completion("ai_analysis", "failed", time.perf_counter() - started)
        raise


async def _execute_ai_analysis(video_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        notifier = RedisStatusNotifier(settings.redis_url)
        tracker = JobTracker(SQLAlchemyJobRepository(session))
        job = await tracker.begin(video_id, "ai_analysis", f"{video_id}:ai_analysis")
        if job is None:
            await session.commit()
            return

        service = AnalysisService(
            videos=SQLAlchemyVideoRepository(session),
            transcripts=SQLAlchemyTranscriptRepository(session),
            analysis_results=SQLAlchemyAnalysisResultRepository(session),
            ai=_container.ai,
            storage=_container.storage,
            notifier=notifier,
        )
        try:
            await service.run_analysis(video_id)
        except Exception as exc:
            logger.exception("ai_analysis_failed", video_id=str(video_id))
            await tracker.fail(job.id, str(exc))
            await session.commit()
            await notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "failed",
                    "stage": "ai_analysis",
                    "message": str(exc)[:500],
                }
            )
            await _emit(EVENT_VIDEO_FAILED, video_id, _failure_payload("ai_analysis", exc))
            raise

        await tracker.succeed(job.id)
        await session.commit()
        await _emit(EVENT_VIDEO_ANALYZED, video_id, {})
        logger.info("ai_analysis_complete", video_id=str(video_id))

    _enqueue("clip_extraction", {"video_id": str(video_id)}, queue=QUEUE_DEFAULT)


# ---------------------------------------------------------------------------
# clip_extraction
# ---------------------------------------------------------------------------


@task(queue=QUEUE_DEFAULT, max_retries=5, max_backoff=60_000)
def clip_extraction(payload: dict[str, Any]) -> None:
    asyncio.run(_run_clip_extraction(payload))


async def _run_clip_extraction(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span("pipeline.clip_extraction") as span:
            span.set_attribute("video_id", str(video_id))
            with logging_mod.request_context(
                video_id=str(video_id),
                stage="clip_extraction",
                trace_id=trace_id_from_context() or "none",
            ):
                await _execute_clip_extraction(video_id)
        record_job_completion("clip_extraction", "succeeded", time.perf_counter() - started)
    except Exception:
        record_job_completion("clip_extraction", "failed", time.perf_counter() - started)
        raise


async def _execute_clip_extraction(video_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        notifier = RedisStatusNotifier(settings.redis_url)
        tracker = JobTracker(SQLAlchemyJobRepository(session))
        job = await tracker.begin(video_id, "clip_extraction", f"{video_id}:clip_extraction")
        if job is None:
            await session.commit()
            return

        videos_repo = SQLAlchemyVideoRepository(session)
        video = await videos_repo.get_by_id(video_id)
        if video is None:
            logger.warning("video_not_found_for_clip_extraction", video_id=str(video_id))
            return

        analysis_repo = SQLAlchemyAnalysisResultRepository(session)
        analysis = await analysis_repo.get_by_video_id(video_id)
        if analysis is None:
            logger.warning("no_analysis_result", video_id=str(video_id))
            return

        editing_plan = analysis.editing_plan
        clip_service = ClipService(
            clips=SQLAlchemyClipRepository(session),
            storage=_container.storage,
            notifier=notifier,
        )
        clips = await clip_service.create_clips_from_editing_plan(
            video_id=video.id,
            project_id=video.project_id,
            editing_plan=editing_plan,
        )
        await session.commit()
        await _emit(EVENT_VIDEO_CLIPS_CREATED, video_id, {"clip_count": len(clips)})

        try:
            path, _, _ = await download_to_tempfile(_container.storage, video.storage_key)
        except Exception as exc:
            logger.exception("clip_extraction_failed", video_id=str(video_id))
            await tracker.fail(job.id, str(exc))
            await session.commit()
            await notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "failed",
                    "stage": "clip_extraction",
                    "message": str(exc)[:500],
                }
            )
            await _emit(EVENT_VIDEO_FAILED, video_id, _failure_payload("clip_extraction", exc))
            raise

        scratch_dir = Path(tempfile.mkdtemp(prefix=f"clips-{video_id}-"))
        cutter = FFmpegCutter()
        thumb_gen = FFmpegThumbnailGenerator()
        try:
            for clip in clips:
                await clip_service.mark_cutting(clip.id)
                await session.commit()

                output_path = str(scratch_dir / f"clip_{clip.id}.mp4")
                thumb_path = str(scratch_dir / f"thumb_{clip.id}.jpg")

                try:
                    await cutter.cut_clip(
                        source_path=str(path),
                        start_seconds=clip.start_seconds,
                        end_seconds=clip.end_seconds,
                        output_path=output_path,
                    )
                    clip_storage_key = f"clips/{clip.id}/clip_{clip.id}.mp4"
                    with open(output_path, "rb") as f:
                        await _container.storage.put(
                            clip_storage_key,
                            f,
                            "video/mp4",
                        )

                    midpoint = clip.start_seconds + (clip.duration_seconds / 2)
                    thumb_key = f"clips/{clip.id}/thumb_{clip.id}.jpg"
                    try:
                        await thumb_gen.generate(
                            source_path=str(path),
                            timestamp_seconds=midpoint,
                            output_path=thumb_path,
                        )
                        with open(thumb_path, "rb") as f:
                            await _container.storage.put(
                                thumb_key,
                                f,
                                "image/jpeg",
                            )
                    except Exception:
                        logger.warning(
                            "thumbnail_generation_failed",
                            clip_id=str(clip.id),
                        )
                        thumb_key = None

                    await clip_service.mark_ready(
                        clip.id, clip_storage_key, thumbnail_storage_key=thumb_key
                    )
                    await session.commit()
                except Exception:
                    logger.exception("clip_extraction_failed", clip_id=str(clip.id))
                    await clip_service.mark_failed(clip.id)
                    await session.commit()
        finally:
            path.unlink(missing_ok=True)
            shutil.rmtree(scratch_dir, ignore_errors=True)

        await tracker.succeed(job.id)
        await session.commit()
        logger.info("clip_extraction_complete", video_id=str(video_id), clip_count=len(clips))

    _enqueue("render", {"video_id": str(video_id)}, queue=QUEUE_RENDER)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


@task(queue=QUEUE_RENDER, max_retries=5, max_backoff=60_000, time_limit=3_600_000)
def render(payload: dict[str, Any]) -> None:
    asyncio.run(_run_render(payload))


async def _run_render(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span("pipeline.render") as span:
            span.set_attribute("video_id", str(video_id))
            with logging_mod.request_context(
                video_id=str(video_id),
                stage="render",
                trace_id=trace_id_from_context() or "none",
            ):
                await _execute_render(video_id)
        record_job_completion("render", "succeeded", time.perf_counter() - started)
    except Exception:
        record_job_completion("render", "failed", time.perf_counter() - started)
        raise


async def _execute_render(video_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        notifier = RedisStatusNotifier(settings.redis_url)
        tracker = JobTracker(SQLAlchemyJobRepository(session))
        job = await tracker.begin(video_id, "render", f"{video_id}:render")
        if job is None:
            await session.commit()
            return

        service = RenderingService(
            clips=SQLAlchemyClipRepository(session),
            transcripts=SQLAlchemyTranscriptRepository(session),
            analysis_results=SQLAlchemyAnalysisResultRepository(session),
            videos=SQLAlchemyVideoRepository(session),
            storage=_container.storage,
            renderer=FFmpegCaptionRenderer(),
            thumbnails=FFmpegThumbnailGenerator(),
            notifier=notifier,
            framing=OpenCVFramingAnalyzer(),
            artifacts=SQLAlchemyArtifactRepository(session),
            artifact_store=StorageArtifactStore(_container.storage),
            caption_engine=settings.caption_engine,
        )
        try:
            rendered, skipped = await service.render_clips_with_captions(video_id)
        except Exception as exc:
            logger.exception("render_failed", video_id=str(video_id))
            await tracker.fail(job.id, str(exc))
            await session.commit()
            await notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "failed",
                    "stage": "render",
                    "message": str(exc)[:500],
                }
            )
            await _emit(EVENT_VIDEO_FAILED, video_id, _failure_payload("render", exc))
            raise

        await tracker.succeed(job.id)
        videos_repo = SQLAlchemyVideoRepository(session)
        await videos_repo.update_status(video_id, "ready")
        await session.commit()
        await _emit(
            EVENT_VIDEO_CLIPS_RENDERED,
            video_id,
            {"rendered_clips": rendered, "skipped": skipped},
        )
        await _emit(EVENT_VIDEO_READY, video_id, {"clip_count": rendered})
        logger.info(
            "render_complete",
            video_id=str(video_id),
            rendered=rendered,
            skipped=skipped,
        )


# ---------------------------------------------------------------------------
# youtube_import
# ---------------------------------------------------------------------------


@task(queue=QUEUE_IMPORT, max_retries=5, max_backoff=60_000)
def youtube_import(payload: dict[str, Any]) -> None:
    asyncio.run(_run_youtube_import(payload))


async def _run_youtube_import(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    url = str(payload["url"])
    started = time.perf_counter()
    try:
        with tracer.start_as_current_span("pipeline.youtube_import") as span:
            span.set_attribute("video_id", str(video_id))
            with logging_mod.request_context(
                video_id=str(video_id),
                stage="youtube_import",
                trace_id=trace_id_from_context() or "none",
            ):
                await _execute_youtube_import(video_id, url)
        record_job_completion("youtube_import", "succeeded", time.perf_counter() - started)
    except Exception:
        record_job_completion("youtube_import", "failed", time.perf_counter() - started)
        raise


async def _execute_youtube_import(video_id: uuid.UUID, url: str) -> None:
    async with SessionLocal() as session:
        notifier = RedisStatusNotifier(settings.redis_url)
        videos_repo = SQLAlchemyVideoRepository(session)
        video = await videos_repo.get_by_id(video_id)
        if video is None:
            logger.warning("video_not_found_for_import", video_id=str(video_id))
            return

        downloader = YouTubeDownloader()
        tmpdir = Path(tempfile.mkdtemp(prefix=f"youtube-{video_id}-"))
        try:
            await notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "importing",
                    "stage": "youtube_download",
                    "message": "Downloading from YouTube...",
                }
            )
            result = await downloader.download(url, tmpdir)

            probe = await asyncio.to_thread(run_ffprobe, result.path)
            metadata = build_metadata(probe)
            checksum = sha256_file(result.path)
            size_bytes = result.path.stat().st_size
            duration = result.duration_seconds or metadata["format"].get("duration")

            with result.path.open("rb") as fh:
                await _container.storage.put(video.storage_key, fh, "video/mp4")

            await videos_repo.update_imported(
                video.id,
                original_filename=f"{result.title}.mp4",
                checksum=checksum,
                size_bytes=size_bytes,
                duration_seconds=duration,
                metadata_json=metadata,
                status="uploaded",
            )
            await session.commit()

            await notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "uploaded",
                    "stage": "youtube_download",
                    "message": f"Downloaded: {result.title}",
                }
            )
            await _emit(EVENT_VIDEO_IMPORTED, video_id, {"title": result.title})
            logger.info(
                "youtube_import_complete",
                video_id=str(video_id),
                title=result.title,
                size_bytes=size_bytes,
            )
        except Exception as exc:
            logger.exception("youtube_import_failed", video_id=str(video_id))
            try:
                await videos_repo.update_status(video_id, "failed")
                await session.commit()
            except Exception:
                logger.exception("failed_to_mark_import_failed", video_id=str(video_id))
            try:
                await notifier.publish(
                    {
                        "video_id": str(video_id),
                        "status": "failed",
                        "stage": "youtube_download",
                        "message": str(exc)[:500],
                    }
                )
            except Exception:
                logger.exception("failed_to_publish_import_failure", video_id=str(video_id))
            await _emit(EVENT_VIDEO_FAILED, video_id, _failure_payload("youtube_download", exc))
            raise
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# dead_letter
# ---------------------------------------------------------------------------


@task(queue=QUEUE_DEAD, max_retries=0, on_retry_exhausted=None)
def dead_letter(message: dict[str, Any], retry_info: dict[str, Any]) -> None:
    asyncio.run(_run_dead_letter(message, retry_info))


async def _run_dead_letter(message: dict[str, Any], retry_info: dict[str, Any]) -> None:
    actor_name = str(message.get("actor_name", "unknown"))
    kwargs = message.get("kwargs") or {}
    payload = kwargs.get("payload") or {}
    queue = str(message.get("queue_name", QUEUE_DEFAULT))
    error = str(message.get("options", {}).get("traceback", "retries exhausted"))

    store = RedisDeadLetterStore(settings.redis_url)
    entry_id = await store.add(
        actor_name=actor_name,
        payload=payload,
        queue=queue,
        message=message,
        error=error,
    )
    logger.error(
        "dead_lettered",
        entry_id=entry_id,
        actor=actor_name,
        queue=queue,
        retries=retry_info.get("retries"),
        video_id=payload.get("video_id"),
    )

    video_id = payload.get("video_id")
    if video_id:
        await _emit(
            EVENT_JOB_DEAD_LETTERED,
            str(video_id),
            {"actor": actor_name, "error": error[:500], "entry_id": entry_id},
        )
        try:
            async with SessionLocal() as session:
                repo = SQLAlchemyVideoRepository(session)
                await repo.update_status(uuid.UUID(str(video_id)), "failed")
                await session.commit()
        except Exception:
            logger.exception("failed_to_mark_video_failed", video_id=str(video_id))
        try:
            notifier = RedisStatusNotifier(settings.redis_url)
            await notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": "failed",
                    "stage": str(payload.get("stage") or actor_name),
                    "message": error[:500],
                }
            )
        except Exception:
            logger.exception("failed_to_publish_dead_letter_status", video_id=str(video_id))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _failure_payload(stage: str, exc: Exception) -> dict[str, Any]:
    return {"stage": stage, "error": str(exc)[:500]}


def _enqueue(task_name: str, payload: dict[str, Any], queue: str = QUEUE_DEFAULT) -> None:
    # Route through the broker port: send_with_options(queue_name=...) is
    # silently ignored by dramatiq 2.x, which pins messages to the actor's
    # default queue. Constructing the Message with an explicit queue guarantees
    # priority routing works.
    _container.queue.enqueue(task_name, payload, queue=queue)


async def _emit(event_type: str, video_id: uuid.UUID, payload: dict[str, Any]) -> None:
    try:
        await _container.events.publish(
            DomainEvent(
                type=event_type,
                aggregate_id=str(video_id),
                payload=payload,
            )
        )
    except Exception:
        logger.warning(
            "event publish failed; continuing",
            event_type=event_type,
            video_id=str(video_id),
        )
