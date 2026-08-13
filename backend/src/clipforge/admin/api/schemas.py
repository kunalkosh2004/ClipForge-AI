import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    type: str
    status: str
    attempts: int
    max_attempts: int
    dedupe_key: str | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedJobResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


class DeadLetterResponse(BaseModel):
    id: str
    actor_name: str
    queue: str
    payload: dict[str, Any]
    error: str
    dead_at: datetime


class JobRetryResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str
