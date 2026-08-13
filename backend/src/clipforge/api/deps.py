import uuid
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.common.errors import ForbiddenError
from clipforge.common.ports import AIProvider, CacheProvider, QueueBroker, StorageProvider
from clipforge.common.ports.event_bus import EventBus
from clipforge.config import Settings
from clipforge.config import get_settings as get_app_settings
from clipforge.container import Container
from clipforge.identity.domain.entities import User
from clipforge.videos.infrastructure.repositories import SQLAlchemyVideoRepository


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


def get_settings() -> Settings:
    return get_app_settings()


def get_storage(request: Request) -> StorageProvider:
    return get_container(request).storage


def get_queue(request: Request) -> QueueBroker:
    return get_container(request).queue


def get_cache(request: Request) -> CacheProvider:
    return get_container(request).cache


def get_events(request: Request) -> EventBus:
    return get_container(request).events


def get_ai(request: Request) -> AIProvider:
    return get_container(request).ai


async def require_owned_video(
    video_id: uuid.UUID,
    user: User,
    session: AsyncSession,
) -> None:
    repo = SQLAlchemyVideoRepository(session)
    video = await repo.get_owned(video_id, user.id)
    if video is None:
        raise ForbiddenError("video not found or access denied")


SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[StorageProvider, Depends(get_storage)]
QueueDep = Annotated[QueueBroker, Depends(get_queue)]
CacheDep = Annotated[CacheProvider, Depends(get_cache)]
AIDep = Annotated[AIProvider, Depends(get_ai)]
EventBusDep = Annotated[EventBus, Depends(get_events)]
