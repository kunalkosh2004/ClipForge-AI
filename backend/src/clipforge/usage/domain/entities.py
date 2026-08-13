import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from clipforge.common.ids import uuid7


@dataclass
class AIModelUsageRecord:
    model: str
    operation: str
    prompt_tokens: int
    response_tokens: int
    total_tokens: int
    date: date
    key: str | None = None
    video_id: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=uuid7)
    created_at: datetime | None = None
