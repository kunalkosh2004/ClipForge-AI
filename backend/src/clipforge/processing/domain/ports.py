import uuid
from abc import ABC, abstractmethod
from typing import Any

from clipforge.common.pagination import PageRequest, PageResult
from clipforge.processing.domain.entities import Job


class JobRepository(ABC):
    @abstractmethod
    async def get_by_dedupe_key(self, dedupe_key: str) -> Job | None:
        """Return the job matching a dedupe key, or None."""

    @abstractmethod
    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        """Return the job matching an id, or None."""

    @abstractmethod
    async def list_all(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        video_id: uuid.UUID | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Job]:
        """Return jobs matching the filters, newest first, with pagination."""

    @abstractmethod
    async def create(self, job: Job) -> Job:
        """Persist a job and return it with generated fields populated."""

    @abstractmethod
    async def mark_running(self, job_id: uuid.UUID) -> Job | None:
        """Set the job running and bump the attempt counter."""

    @abstractmethod
    async def mark_succeeded(self, job_id: uuid.UUID) -> Job | None:
        """Mark the job succeeded."""

    @abstractmethod
    async def mark_failed(self, job_id: uuid.UUID, error: str) -> Job | None:
        """Mark the job failed, recording the error message."""


class StatusNotifier(ABC):
    @abstractmethod
    async def publish(self, event: dict[str, Any]) -> None:
        """Publish a pipeline status event. Best-effort by design."""
