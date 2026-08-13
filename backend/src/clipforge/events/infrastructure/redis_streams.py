import json
from typing import Any

import redis.asyncio as aioredis

from clipforge.common.events import DomainEvent
from clipforge.common.ports.event_bus import EventBus

MAXLEN = 10_000


class RedisStreamsEventBus(EventBus):
    """Durable event log backed by a single Redis stream.

    Trade-offs:
    - A single global stream preserves global ordering and is easy to tail.
    - `XADD` with approximate maxlen keeps memory bounded without blocking.
    - Redis Streams are not transactional with Postgres; publishing is
      best-effort. A transactional outbox relay can be added later without
      changing this interface.
    - Each call uses a fresh client: worker tasks run in their own asyncio
      loop (asyncio.run), so a pooled connection from another loop would fail.
    """

    def __init__(self, redis_url: str, stream: str = "clipforge:events") -> None:
        self._redis_url = redis_url
        self._stream = stream

    async def publish(self, event: DomainEvent) -> None:
        record = event.to_record()
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            await client.xadd(
                self._stream,
                {
                    "id": record["id"],
                    "type": record["type"],
                    "aggregate_id": record["aggregate_id"],
                    "occurred_at": record["occurred_at"],
                    "data": json.dumps(record),
                },
                maxlen=MAXLEN,
                approximate=True,
            )
        finally:
            await client.aclose()

    async def list_events(
        self,
        aggregate_id: str | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            entries = await client.xrevrange(self._stream, max="-", min="+", count=limit)
            events = [_event_from_entry(entry_id, fields) for entry_id, fields in entries]
        finally:
            await client.aclose()
        if aggregate_id is None:
            return events
        return [event for event in events if event.aggregate_id == aggregate_id]

    async def read_after(
        self,
        cursor: str,
        aggregate_id: str | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            entries = await client.xrange(
                self._stream,
                min=f"({cursor}",
                max="+",
                count=limit,
            )
            events = [_event_from_entry(entry_id, fields) for entry_id, fields in entries]
        finally:
            await client.aclose()
        if aggregate_id is None:
            return events
        return [event for event in events if event.aggregate_id == aggregate_id]


def _event_from_entry(entry_id: str, fields: dict[str, Any]) -> DomainEvent:
    record = json.loads(fields["data"])
    metadata = dict(record.get("metadata") or {})
    metadata["stream_id"] = entry_id
    return DomainEvent(
        type=record["type"],
        aggregate_id=record["aggregate_id"],
        payload=record.get("payload") or {},
        metadata=metadata,
        occurred_at=record["occurred_at"],
        id=record["id"],
    )
