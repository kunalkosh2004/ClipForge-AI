import json
from typing import Any

import redis.asyncio as aioredis

from clipforge.processing.domain.ports import StatusNotifier


class RedisStatusNotifier(StatusNotifier):
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def publish(self, event: dict[str, Any]) -> None:
        # A fresh client per publish: each dramatiq task runs in its own event
        # loop (asyncio.run), so a pooled connection from a previous loop would
        # fail with "Event loop is closed".
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            await client.publish("clipforge:status", json.dumps(event))
        finally:
            await client.aclose()
