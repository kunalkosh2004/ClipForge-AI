import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.analysis.application.schemas import AnalysisResultResponse, TranscriptResponse
from clipforge.analysis.application.service import AnalysisService
from clipforge.analysis.domain.presets import list_presets
from clipforge.analysis.infrastructure.repositories import (
    SQLAlchemyAnalysisResultRepository,
    SQLAlchemyTranscriptRepository,
)
from clipforge.analysis.infrastructure.subtitles import segments_to_srt, segments_to_vtt
from clipforge.api.deps import get_container, require_owned_video
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.processing.infrastructure.status import RedisStatusNotifier
from clipforge.videos.infrastructure.repositories import SQLAlchemyVideoRepository

router = APIRouter(tags=["analysis"])


@router.get("/presets")
async def get_presets(
    user: CurrentUser,
) -> list[dict]:
    return list_presets()


def _service(request: Request, session: AsyncSession) -> AnalysisService:
    container = get_container(request)
    return AnalysisService(
        videos=SQLAlchemyVideoRepository(session),
        transcripts=SQLAlchemyTranscriptRepository(session),
        analysis_results=SQLAlchemyAnalysisResultRepository(session),
        ai=container.ai,
        storage=container.storage,
        notifier=RedisStatusNotifier(container.settings.redis_url),
    )


@router.get(
    "/videos/{video_id}/transcript",
    response_model=TranscriptResponse,
)
async def get_transcript(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> TranscriptResponse:
    await require_owned_video(video_id, user, session)
    svc = _service(request, session)
    transcript = await svc.get_transcript(video_id)
    return TranscriptResponse(
        id=transcript.id,
        video_id=transcript.video_id,
        language=transcript.language,
        segments=transcript.segments,
        words=transcript.words,
        created_at=transcript.created_at,
    )


@router.get(
    "/videos/{video_id}/analysis",
    response_model=AnalysisResultResponse,
)
async def get_analysis(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> AnalysisResultResponse:
    await require_owned_video(video_id, user, session)
    svc = _service(request, session)
    result = await svc.get_analysis_result(video_id)
    return AnalysisResultResponse(
        id=result.id,
        video_id=result.video_id,
        understanding=result.understanding,
        editing_plan=result.editing_plan,
        editing_blueprint=result.editing_blueprint,
        ai_model=result.ai_model,
        ai_cost_cents=result.ai_cost_cents,
        created_at=result.created_at,
    )


@router.get("/videos/{video_id}/subtitles")
async def download_subtitles(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    format: str = Query("srt", regex="^(srt|vtt)$"),
) -> PlainTextResponse:
    await require_owned_video(video_id, user, session)
    svc = _service(request, session)
    transcript = await svc.get_transcript(video_id)
    if format == "vtt":
        content = segments_to_vtt(transcript.segments)
        media_type = "text/vtt"
    else:
        content = segments_to_srt(transcript.segments)
        media_type = "application/x-subrip"
    return PlainTextResponse(content=content, media_type=media_type)
