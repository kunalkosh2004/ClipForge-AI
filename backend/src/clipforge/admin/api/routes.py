import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.admin.api.deps import AdminUser
from clipforge.admin.api.schemas import (
    DeadLetterResponse,
    JobResponse,
    JobRetryResponse,
    PaginatedJobResponse,
)
from clipforge.admin.application.service import AdminService
from clipforge.admin.infrastructure.dead_letters import RedisDeadLetterStore
from clipforge.api.deps import get_container
from clipforge.common.pagination import PageRequest
from clipforge.db.session import get_db
from clipforge.processing.infrastructure.repositories import SQLAlchemyJobRepository
from clipforge.videos.infrastructure.repositories import SQLAlchemyVideoRepository

router = APIRouter(tags=["admin"])


def _service(request: Request, session: AsyncSession) -> AdminService:
    container = get_container(request)
    return AdminService(
        jobs=SQLAlchemyJobRepository(session),
        videos=SQLAlchemyVideoRepository(session),
        queue=container.queue,
        dead_letters=RedisDeadLetterStore(container.settings.redis_url),
    )


@router.get(
    "/admin/jobs",
    response_model=PaginatedJobResponse[JobResponse],
)
async def list_jobs(
    request: Request,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    job_type: str | None = Query(None),
    video_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedJobResponse[JobResponse]:
    page = PageRequest.from_query(limit=limit, offset=offset)
    result = await _service(request, session).list_jobs(
        status=status_filter,
        job_type=job_type,
        video_id=video_id,
        page=page,
    )
    return PaginatedJobResponse(
        items=[
            JobResponse(
                id=job.id,
                video_id=job.video_id,
                type=job.type,
                status=job.status,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
                dedupe_key=job.dedupe_key,
                last_error=job.last_error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            for job in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.post(
    "/admin/jobs/{job_id}/retry",
    response_model=JobRetryResponse,
)
async def retry_job(
    job_id: uuid.UUID,
    request: Request,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_db),
) -> JobRetryResponse:
    job = await _service(request, session).retry_job(job_id)
    return JobRetryResponse(id=job.id, status=job.status, message="job requeued")


@router.get(
    "/admin/dead-letters",
    response_model=list[DeadLetterResponse],
)
async def list_dead_letters(
    request: Request,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
) -> list[DeadLetterResponse]:
    entries = await _service(request, session).list_dead_letters(limit=limit)
    return [
        DeadLetterResponse(
            id=entry["id"],
            actor_name=entry["actor_name"],
            queue=entry["queue"],
            payload=entry["payload"],
            error=entry["error"],
            dead_at=entry["dead_at"],
        )
        for entry in entries
    ]


@router.post(
    "/admin/dead-letters/{entry_id}/retry",
    response_model=DeadLetterResponse,
)
async def retry_dead_letter(
    entry_id: str,
    request: Request,
    _admin: AdminUser,
    session: AsyncSession = Depends(get_db),
) -> DeadLetterResponse:
    entry = await _service(request, session).retry_dead_letter(entry_id)
    return DeadLetterResponse(
        id=entry["id"],
        actor_name=entry["actor_name"],
        queue=entry["queue"],
        payload=entry["payload"],
        error=entry["error"],
        dead_at=entry["dead_at"],
    )


@router.delete(
    "/admin/dead-letters/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_dead_letter(
    entry_id: str,
    request: Request,
    _admin: AdminUser,
) -> None:
    store = RedisDeadLetterStore(get_container(request).settings.redis_url)
    await store.remove(entry_id)
