from abc import ABC, abstractmethod

from clipforge.common.events import DomainEvent


class EventBus(ABC):
    """Durable event log. Publishes domain events and allows them to be read
    back for auditing, debugging and replay.

    Implementations must be safe to call from any event loop (the API process
    and dramatiq worker tasks run in different asyncio loops).
    """

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Append an event to the log. Best-effort: failures are logged, not
        fatal to the pipeline."""

    @abstractmethod
    async def list_events(
        self,
        aggregate_id: str | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        """Return the most recent events, newest first. Optionally filtered to
        a single aggregate (e.g. a video)."""

    @abstractmethod
    async def read_after(
        self,
        cursor: str,
        aggregate_id: str | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        """Return events appended after a stream cursor, oldest first. Used for
        tailing/replay. `cursor` is an opaque value previously returned in
        `DomainEvent.metadata["stream_id"]`."""
