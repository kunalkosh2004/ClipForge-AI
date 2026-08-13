import uuid
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime


class PaginatedProjectResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool


class CreateVideoRequest(BaseModel):
    project_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(gt=0, le=1_073_741_824)


class UpdateVideoRequest(BaseModel):
    editing_style: str | None = Field(default=None, max_length=2000)


class ImportVideoRequest(BaseModel):
    project_id: uuid.UUID
    url: str = Field(min_length=8, max_length=2048)
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ImportVideoResponse(BaseModel):
    video_id: uuid.UUID
    status: str


class StartUploadResponse(BaseModel):
    video_id: uuid.UUID
    storage_key: str
    upload_url: str
    expires_in: int


class CompleteUploadResponse(BaseModel):
    video_id: uuid.UUID
    status: str


class VideoResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    original_filename: str
    source_url: str | None
    storage_key: str
    content_type: str
    size_bytes: int
    checksum: str | None
    duration_seconds: float | None
    editing_style: str | None
    status: str
    created_at: datetime


class PaginatedVideoResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_more: bool
