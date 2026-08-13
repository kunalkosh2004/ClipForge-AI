import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from clipforge.common.ids import uuid7


@dataclass(frozen=True)
class TranscriptRecord:
    video_id: uuid.UUID
    language: str
    segments: list[dict[str, Any]] = field(default_factory=list)
    words: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)


@dataclass(frozen=True)
class AnalysisResultRecord:
    video_id: uuid.UUID
    understanding: dict[str, Any]
    editing_plan: dict[str, Any]
    ai_model: str
    editing_blueprint: dict[str, Any] | None = None
    ai_cost_cents: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)
