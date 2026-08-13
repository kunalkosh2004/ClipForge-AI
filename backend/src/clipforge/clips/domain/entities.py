import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from clipforge.common.ids import uuid7


@dataclass(frozen=True)
class Clip:
    video_id: uuid.UUID
    project_id: uuid.UUID
    title: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    storage_key: str | None = None
    render_storage_key: str | None = None
    thumbnail_storage_key: str | None = None
    editing_plan_json: dict[str, Any] | None = None
    format: str | None = None
    status: str = "pending"
    rendered: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)
