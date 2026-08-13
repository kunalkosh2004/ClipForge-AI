import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.api.deps import get_container, require_owned_video
from clipforge.artifacts.infrastructure.repositories import SQLAlchemyArtifactRepository
from clipforge.artifacts.infrastructure.storage_store import StorageArtifactStore
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.timeline.api.schemas import TimelineResponse
from clipforge.timeline.application.service import TimelineService

router = APIRouter(tags=["timeline"])


@router.get("/videos/{video_id}/timeline", response_model=TimelineResponse)
async def get_timeline(
    video_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    await require_owned_video(video_id, user, session)
    container = get_container(request)
    service = TimelineService(
        artifacts=SQLAlchemyArtifactRepository(session),
        store=StorageArtifactStore(container.storage),
    )
    return TimelineResponse(**await service.get_timeline(video_id))
