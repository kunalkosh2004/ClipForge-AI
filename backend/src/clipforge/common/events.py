import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from clipforge.common.ids import uuid7

# Domain event types published to the event bus.
EVENT_VIDEO_UPLOADED = "video.uploaded"
EVENT_VIDEO_IMPORT_QUEUED = "video.import_queued"
EVENT_VIDEO_IMPORTED = "video.imported"
EVENT_VIDEO_METADATA_EXTRACTED = "video.metadata_extracted"
EVENT_VIDEO_ANALYZED = "video.analyzed"
EVENT_VIDEO_CLIPS_CREATED = "video.clips_created"
EVENT_VIDEO_CLIPS_RENDERED = "video.rendered"
EVENT_VIDEO_READY = "video.ready"
EVENT_VIDEO_FAILED = "video.failed"
EVENT_JOB_DEAD_LETTERED = "job.dead_lettered"

# Intelligence worker events (artifact pipeline). Per-kind completion events
# let the Workflow Engine advance the DAG; `worker.failed` carries `kind`.
EVENT_METADATA_COMPLETED = "worker.metadata.completed"
EVENT_SCENE_COMPLETED = "worker.scene.completed"
EVENT_MOTION_COMPLETED = "worker.motion.completed"
EVENT_BEAT_COMPLETED = "worker.beat.completed"
EVENT_WORKER_FAILED = "worker.failed"

WORKER_COMPLETED_EVENT_BY_KIND = {
    "metadata": EVENT_METADATA_COMPLETED,
    "scene": EVENT_SCENE_COMPLETED,
    "motion": EVENT_MOTION_COMPLETED,
    "beat": EVENT_BEAT_COMPLETED,
}


def worker_completed_event(kind: str) -> str:
    """Map a worker kind to its completion event type."""
    return WORKER_COMPLETED_EVENT_BY_KIND.get(kind, f"worker.{kind}.completed")


@dataclass(frozen=True)
class DomainEvent:
    """An immutable fact that happened in the system.

    Events are append-only facts (never updated/deleted) and form the durable
    audit log of the platform. Subscribers may react to them (notifications,
    analytics, dead-letter recovery, replay).
    """

    type: str
    aggregate_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: uuid.UUID = field(default_factory=uuid7)

    def to_record(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": self.type,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
            "metadata": self.metadata,
        }
