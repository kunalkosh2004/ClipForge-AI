import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.api.deps import get_container
from clipforge.common.pagination import PageRequest
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.videos.application.schemas import (
    CompleteUploadResponse,
    CreateProjectRequest,
    CreateVideoRequest,
    ImportVideoRequest,
    ImportVideoResponse,
    PaginatedProjectResponse,
    PaginatedVideoResponse,
    ProjectResponse,
    StartUploadResponse,
    UpdateVideoRequest,
    VideoResponse,
)
from clipforge.videos.application.service import VideoService
from clipforge.videos.infrastructure.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyVideoRepository,
)

router = APIRouter(tags=["videos"])


def _service(request: Request, session: AsyncSession) -> VideoService:
    container = get_container(request)
    return VideoService(
        projects=SQLAlchemyProjectRepository(session),
        videos=SQLAlchemyVideoRepository(session),
        storage=container.storage,
        queue=container.queue,
        events=container.events,
        media_queue=container.settings.queue_media,
        default_queue=container.settings.queue_default,
    )


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: CreateProjectRequest,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await _service(request, session).create_project(user.id, payload.name)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        status=project.status,
        created_at=project.created_at,
    )


@router.get("/projects", response_model=PaginatedProjectResponse[ProjectResponse])
async def list_projects(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedProjectResponse[ProjectResponse]:
    page = PageRequest.from_query(limit=limit, offset=offset)
    result = await _service(request, session).list_projects(user.id, page)
    return PaginatedProjectResponse(
        items=[
            ProjectResponse(
                id=p.id,
                name=p.name,
                status=p.status,
                created_at=p.created_at,
            )
            for p in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    await _service(request, session).delete_project(user.id, project_id)


@router.get(
    "/projects/{project_id}/videos",
    response_model=PaginatedVideoResponse[VideoResponse],
)
async def list_videos_for_project(
    project_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedVideoResponse[VideoResponse]:
    page = PageRequest.from_query(limit=limit, offset=offset)
    result = await _service(request, session).list_videos(user.id, project_id, page)
    return PaginatedVideoResponse(
        items=[
            VideoResponse(
                id=v.id,
                project_id=v.project_id,
                original_filename=v.original_filename,
                source_url=v.source_url,
                storage_key=v.storage_key,
                content_type=v.content_type,
                size_bytes=v.size_bytes,
                checksum=v.checksum,
                duration_seconds=v.duration_seconds,
                editing_style=v.editing_style,
                status=v.status,
                created_at=v.created_at,
            )
            for v in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.post("/videos", response_model=StartUploadResponse, status_code=status.HTTP_201_CREATED)
async def start_upload(
    payload: CreateVideoRequest,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> StartUploadResponse:
    return await _service(request, session).start_upload(user.id, payload)


@router.post(
    "/videos/import", response_model=ImportVideoResponse, status_code=status.HTTP_201_CREATED
)
async def import_video(
    payload: ImportVideoRequest,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> ImportVideoResponse:
    return await _service(request, session).import_from_youtube(user.id, payload)


@router.post("/videos/{video_id}/complete", response_model=CompleteUploadResponse)
async def complete_upload(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> CompleteUploadResponse:
    return await _service(request, session).complete_upload(user.id, video_id)


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> VideoResponse:
    return await _service(request, session).get_video(user.id, video_id)


@router.patch("/videos/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: uuid.UUID,
    payload: UpdateVideoRequest,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> VideoResponse:
    return await _service(request, session).update_video(
        user.id, video_id, payload.editing_style
    )


@router.post(
    "/videos/{video_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict[str, str],
)
async def process_video(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Start full processing for a stored video (metadata -> AI analysis ->
    clip extraction -> render, plus the artifact intelligence workflow)."""
    await _service(request, session).process_video(user.id, video_id)
    return {"status": "processing"}


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> None:
    await _service(request, session).delete_video(user.id, video_id)


@router.post(
    "/videos/{video_id}/intelligence/start",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict[str, str],
)
async def start_intelligence(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Start the artifact pipeline (Metadata -> Scene/Motion/Beat in
    parallel) for a video. Idempotent: re-running advances only what is
    missing or stale."""
    await _service(request, session).start_intelligence(user.id, video_id)
    return {"status": "started"}
