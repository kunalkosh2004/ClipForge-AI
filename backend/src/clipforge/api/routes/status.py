import json
import uuid
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from clipforge.common.errors import EntityNotFoundError
from clipforge.config import get_settings
from clipforge.db.session import get_db
from clipforge.identity.api.deps import CurrentUser
from clipforge.videos.infrastructure.repositories import SQLAlchemyVideoRepository

router = APIRouter(tags=["status"])


async def _status_event_generator(
    video_id: str, redis_url: str
) -> AsyncGenerator[dict, None]:
    client = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe("clipforge:status")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("video_id") != video_id:
                continue
            yield {
                "event": "status",
                "data": json.dumps(data),
            }
            if data.get("status") in ("ready", "failed"):
                yield {
                    "event": "complete",
                    "data": json.dumps(data),
                }
                break
    finally:
        await pubsub.unsubscribe("clipforge:status")
        await client.aclose()


@router.get("/videos/{video_id}/stream")
async def stream_status(
    video_id: str,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    repo = SQLAlchemyVideoRepository(session)
    video = await repo.get_owned(uuid.UUID(video_id), user.id)
    if video is None:
        raise EntityNotFoundError("video not found")
    settings = get_settings()
    return EventSourceResponse(
        _status_event_generator(video_id, settings.redis_url),
        media_type="text/event-stream",
    )
