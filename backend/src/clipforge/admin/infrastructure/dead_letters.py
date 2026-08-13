import json
import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

KEY = "clipforge:dead_letters"


class RedisDeadLetterStore:
    """Persist exhausted messages for admin inspection and manual retry.

    Entries are stored as a Redis list of JSON records (newest first). A fresh
    client is used per call so the store works from both the API process and
    dramatiq task event loops.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def add(
        self,
        *,
        actor_name: str,
        payload: dict[str, Any],
        queue: str,
        message: dict[str, Any],
        error: str,
    ) -> str:
        entry_id = str(uuid.uuid4())
        record = {
            "id": entry_id,
            "actor_name": actor_name,
            "queue": queue,
            "payload": payload,
            "message": message,
            "error": error[:2000],
            "dead_at": datetime.now(UTC).isoformat(),
        }
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            await client.lpush(KEY, json.dumps(record))
        finally:
            await client.aclose()
        return entry_id

    async def list(self, limit: int = 100) -> list[dict[str, Any]]:
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            raw = await client.lrange(KEY, 0, limit - 1)
        finally:
            await client.aclose()
        entries = []
        for item in raw:
            try:
                entries.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                continue
        return entries

    async def get(self, entry_id: str) -> dict[str, Any] | None:
        for entry in await self.list(limit=500):
            if entry.get("id") == entry_id:
                return entry
        return None

    async def remove(self, entry_id: str) -> bool:
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            for item in await client.lrange(KEY, 0, -1):
                try:
                    entry = json.loads(item)
                except (json.JSONDecodeError, TypeError):
                    continue
                if entry.get("id") == entry_id:
                    removed = await client.lrem(KEY, 1, item)
                    return removed > 0
        finally:
            await client.aclose()
        return False
