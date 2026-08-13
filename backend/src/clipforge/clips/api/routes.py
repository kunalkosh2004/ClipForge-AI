import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.api.deps import get_container, require_owned_video
from clipforge.clips.application.schemas import ClipListResponse, ClipResponse
from clipforge.clips.application.service import ClipService
from clipforge.clips.infrastructure.repositories import SQLAlchemyClipRepository
from clipforge.common.errors import ForbiddenError
from clipforge.common.pagination import PageRequest
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.processing.infrastructure.status import RedisStatusNotifier
from clipforge.videos.infrastructure.repositories import SQLAlchemyProjectRepository

router = APIRouter(tags=["clips"])


def _service(request: Request, session: AsyncSession) -> ClipService:
    container = get_container(request)
    return ClipService(
        clips=SQLAlchemyClipRepository(session),
        storage=container.storage,
        notifier=RedisStatusNotifier(container.settings.redis_url),
    )


@router.get("/videos/{video_id}/clips", response_model=ClipListResponse[ClipResponse])
async def list_clips_for_video(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ClipListResponse[ClipResponse]:
    await require_owned_video(video_id, user, session)
    svc = _service(request, session)
    page = PageRequest.from_query(limit=limit, offset=offset)
    result = await svc.list_clips_for_video(video_id, page)
    return ClipListResponse(
        items=[
            ClipResponse(
                id=c.id,
                video_id=c.video_id,
                project_id=c.project_id,
                title=c.title,
                start_seconds=c.start_seconds,
                end_seconds=c.end_seconds,
                duration_seconds=c.duration_seconds,
                storage_key=c.storage_key,
                render_storage_key=c.render_storage_key,
                thumbnail_storage_key=c.thumbnail_storage_key,
                format=c.format,
                status=c.status,
                rendered=c.rendered,
                created_at=c.created_at,
            )
            for c in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.get("/projects/{project_id}/clips", response_model=ClipListResponse[ClipResponse])
async def list_clips_for_project(
    project_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ClipListResponse[ClipResponse]:
    project_repo = SQLAlchemyProjectRepository(session)
    project = await project_repo.get_by_id(project_id)
    if project is None or project.owner_id != user.id:
        raise ForbiddenError("project not found or access denied")
    svc = _service(request, session)
    page = PageRequest.from_query(limit=limit, offset=offset)
    result = await svc.list_clips_for_project(project_id, page)
    return ClipListResponse(
        items=[
            ClipResponse(
                id=c.id,
                video_id=c.video_id,
                project_id=c.project_id,
                title=c.title,
                start_seconds=c.start_seconds,
                end_seconds=c.end_seconds,
                duration_seconds=c.duration_seconds,
                storage_key=c.storage_key,
                render_storage_key=c.render_storage_key,
                thumbnail_storage_key=c.thumbnail_storage_key,
                format=c.format,
                status=c.status,
                rendered=c.rendered,
                created_at=c.created_at,
            )
            for c in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.get("/clips/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> ClipResponse:
    svc = _service(request, session)
    clip = await svc.get_clip(clip_id)
    await require_owned_video(clip.video_id, user, session)
    return ClipResponse(
        id=clip.id,
        video_id=clip.video_id,
        project_id=clip.project_id,
        title=clip.title,
        start_seconds=clip.start_seconds,
        end_seconds=clip.end_seconds,
        duration_seconds=clip.duration_seconds,
        storage_key=clip.storage_key,
        render_storage_key=clip.render_storage_key,
        thumbnail_storage_key=clip.thumbnail_storage_key,
        format=clip.format,
        status=clip.status,
        rendered=clip.rendered,
        created_at=clip.created_at,
    )


@router.get("/clips/{clip_id}/download")
async def download_clip(
    clip_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict:
    svc = _service(request, session)
    clip = await svc.get_clip(clip_id)
    await require_owned_video(clip.video_id, user, session)
    url = await svc.get_clip_download_url(clip_id)
    return {"download_url": url}


@router.delete("/clips/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clip(
    clip_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    svc = _service(request, session)
    clip = await svc.get_clip(clip_id)
    await require_owned_video(clip.video_id, user, session)
    await svc.delete_clip(clip_id)
