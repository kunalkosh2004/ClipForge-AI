import uuid
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ClipResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    storage_key: str | None
    render_storage_key: str | None = None
    thumbnail_storage_key: str | None = None
    format: str | None = None
    status: str
    rendered: bool = False
    created_at: datetime


class ClipListResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool
