import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TranscriptResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    language: str
    segments: list[dict[str, Any]]
    words: list[dict[str, Any]]
    created_at: datetime


class AnalysisResultResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    understanding: dict[str, Any]
    editing_plan: dict[str, Any]
    editing_blueprint: dict[str, Any] | None = None
    ai_model: str
    ai_cost_cents: int
    created_at: datetime


class AnalysisStatusResponse(BaseModel):
    video_id: uuid.UUID
    stage: str
    status: str
    message: str | None = None
