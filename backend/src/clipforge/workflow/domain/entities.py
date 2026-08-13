import uuid
from dataclasses import dataclass, field
from datetime import datetime

from clipforge.common.ids import uuid7

# Node lifecycle: waiting -> running -> succeeded | failed | skipped
NODE_WAITING = "waiting"
NODE_RUNNING = "running"
NODE_SUCCEEDED = "succeeded"
NODE_FAILED = "failed"
NODE_SKIPPED = "skipped"

SATISFIED_STATUSES = (NODE_SUCCEEDED, NODE_SKIPPED)
ACTIVE_STATUSES = (NODE_WAITING, NODE_RUNNING)


@dataclass(frozen=True)
class WorkflowNode:
    """A single step of a video's intelligence workflow DAG."""

    video_id: uuid.UUID
    kind: str
    depends_on: tuple[str, ...] = ()
    queue: str = "media"
    max_attempts: int = 5
    status: str = NODE_WAITING
    attempts: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    created_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid7)
