import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from clipforge.common.ids import uuid7


@dataclass(frozen=True)
class Project:
    owner_id: uuid.UUID
    name: str
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)


@dataclass(frozen=True)
class Video:
    project_id: uuid.UUID
    original_filename: str
    storage_key: str
    content_type: str
    size_bytes: int
    source_url: str | None = None
    checksum: str | None = None
    duration_seconds: float | None = None
    editing_style: str | None = None
    metadata_json: dict[str, Any] | None = None
    status: str = "pending"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)
