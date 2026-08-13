import uuid
from abc import ABC, abstractmethod

from clipforge.workflow.domain.entities import WorkflowNode


class WorkflowNodeRepository(ABC):
    @abstractmethod
    async def create(self, node: WorkflowNode) -> WorkflowNode:
        ...

    @abstractmethod
    async def get(self, video_id: uuid.UUID, kind: str) -> WorkflowNode | None:
        ...

    @abstractmethod
    async def list_for_video(self, video_id: uuid.UUID) -> list[WorkflowNode]:
        ...

    @abstractmethod
    async def mark_running(self, node_id: uuid.UUID) -> WorkflowNode | None:
        """Set status running, bump attempts, stamp started_at."""

    @abstractmethod
    async def mark_succeeded(self, node_id: uuid.UUID) -> WorkflowNode | None:
        ...

    @abstractmethod
    async def mark_failed(self, node_id: uuid.UUID, error: str) -> WorkflowNode | None:
        ...

    @abstractmethod
    async def mark_skipped(self, node_id: uuid.UUID) -> WorkflowNode | None:
        ...

    @abstractmethod
    async def reset_stale(
        self, video_id: uuid.UUID, max_started_age_seconds: int
    ) -> list[WorkflowNode]:
        """Return running nodes started more than `max_started_age_seconds`
        ago, reset to `waiting` (used for crash recovery)."""
