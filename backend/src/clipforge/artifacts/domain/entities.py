import uuid
from dataclasses import dataclass, field
from datetime import datetime

from clipforge.common.ids import uuid7


@dataclass(frozen=True)
class Artifact:
    """Reference to a computed artifact blob.

    The payload lives in storage at `storage_key`; this object is the metadata
    index used for caching and dedupe. `checksum` is the sha256 of the blob.
    """

    video_id: uuid.UUID
    kind: str
    version: str
    storage_key: str
    checksum: str
    size_bytes: int = 0
    created_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)
