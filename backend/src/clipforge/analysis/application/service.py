import time
import uuid

from clipforge.analysis.domain.entities import AnalysisResultRecord, TranscriptRecord
from clipforge.analysis.domain.ports import AnalysisResultRepository, TranscriptRepository
from clipforge.analysis.domain.presets import get_preset, recommend_preset
from clipforge.common import logging as logging_mod
from clipforge.common.errors import EntityNotFoundError
from clipforge.common.observability import record_ai_call
from clipforge.common.ports import AIProvider, StorageProvider, VideoInput
from clipforge.directing.application.normalizer import normalize_blueprint
from clipforge.directing.application.service import legacy_plan_from_blueprint
from clipforge.processing.domain.ports import StatusNotifier
from clipforge.processing.infrastructure.ffprobe import download_to_tempfile
from clipforge.videos.domain.ports import VideoRepository

logger = logging_mod.get_logger(__name__)


class AnalysisService:
    def __init__(
        self,
        videos: VideoRepository,
        transcripts: TranscriptRepository,
        analysis_results: AnalysisResultRepository,
        ai: AIProvider,
        storage: StorageProvider,
        notifier: StatusNotifier,
    ) -> None:
        self._videos = videos
        self._transcripts = transcripts
        self._analysis_results = analysis_results
        self._ai = ai
        self._storage = storage
        self._notifier = notifier

    async def run_analysis(
        self, video_id: uuid.UUID, preset: str | None = None
    ) -> AnalysisResultRecord:
        video = await self._videos.get_by_id(video_id)
        if video is None:
            raise EntityNotFoundError("video not found")

        await self._notify(video_id, "analyzing", "ai_analysis", "Starting AI analysis")

        path, _, _ = await download_to_tempfile(self._storage, video.storage_key)
        try:
            video_input = VideoInput(
                storage_uri=str(path),
                mime_type=video.content_type,
                duration_seconds=video.duration_seconds,
            )

            model = getattr(self._ai, "MODEL", "unknown")
            provider = type(self._ai).__name__

            started = time.perf_counter()
            understanding = await self._ai.analyze_video(video_input)
            record_ai_call(provider, model, "analyze_video", time.perf_counter() - started)
            await self._notify(
                video_id,
                "analyzing",
                "ai_analysis",
                f"Found {len(understanding.scenes)} scenes, {len(understanding.topics)} topics",
            )

            started = time.perf_counter()
            raw_blueprint = await self._ai.direct(
                video_input,
                preset=preset,
                context=understanding,
                editing_style=video.editing_style,
            )
            record_ai_call(
                provider, model, "direct", time.perf_counter() - started
            )

            plan_preset, preset_confidence = recommend_preset(
                understanding.model_dump(),
                ai_preset=raw_blueprint.preset,
                requested_preset=preset,
            )
            preset_obj = get_preset(plan_preset)
            target_duration = preset_obj.target_duration if preset_obj else None
            # Clamp against the authoritative ffprobe duration from the
            # metadata stage, not the AI's own duration estimate (which can
            # exceed the real video and let out-of-range clips through).
            duration_seconds = video.duration_seconds or understanding.duration_seconds
            blueprint = normalize_blueprint(
                raw_blueprint,
                duration_seconds,
                target_duration=target_duration,
            )
            blueprint = blueprint.model_copy(update={"preset": plan_preset})
            legacy_plan = legacy_plan_from_blueprint(blueprint)
            legacy_plan["preset_confidence"] = preset_confidence

            await self._notify(
                video_id,
                "analyzing",
                "ai_analysis",
                f"{len(blueprint.clips)} clips directed, "
                f"{len(blueprint.timeline.events)} timeline events, transcribing...",
            )

            started = time.perf_counter()
            transcript = await self._ai.transcribe(video_input)
            record_ai_call(provider, model, "transcribe", time.perf_counter() - started)
            transcript_record = TranscriptRecord(
                video_id=video_id,
                language=transcript.language,
                segments=[s.model_dump() for s in transcript.segments],
                words=[
                    w.model_dump() for s in transcript.segments for w in s.words
                ],
            )
            transcript_record = await self._transcripts.create(transcript_record)
        finally:
            path.unlink(missing_ok=True)

        await self._notify(
            video_id,
            "analyzing",
            "ai_analysis",
            "Transcription complete, saving editing plan...",
        )

        ai_model = getattr(self._ai, "MODEL", "unknown")
        result_record = AnalysisResultRecord(
            video_id=video_id,
            understanding=understanding.model_dump(),
            editing_plan=legacy_plan,
            editing_blueprint=blueprint.model_dump(),
            ai_model=ai_model,
        )
        result_record = await self._analysis_results.create(result_record)

        await self._notify(video_id, "analyzing", "ai_analysis", "Analysis complete")
        return result_record

    async def get_transcript(self, video_id: uuid.UUID) -> TranscriptRecord:
        transcript = await self._transcripts.get_by_video_id(video_id)
        if transcript is None:
            raise EntityNotFoundError("transcript not found")
        return transcript

    async def get_analysis_result(self, video_id: uuid.UUID) -> AnalysisResultRecord:
        result = await self._analysis_results.get_by_video_id(video_id)
        if result is None:
            raise EntityNotFoundError("analysis result not found")
        return result

    async def _notify(
        self, video_id: uuid.UUID, status: str, stage: str, message: str
    ) -> None:
        try:
            await self._notifier.publish(
                {
                    "video_id": str(video_id),
                    "status": status,
                    "stage": stage,
                    "message": message,
                }
            )
        except Exception:
            logger.warning("status publish failed; continuing", video_id=str(video_id))
