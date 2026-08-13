import uuid
from dataclasses import dataclass, field
from datetime import datetime

from clipforge.common.ids import uuid7


@dataclass(frozen=True)
class Job:
    video_id: uuid.UUID
    type: str
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    dedupe_key: str | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)
