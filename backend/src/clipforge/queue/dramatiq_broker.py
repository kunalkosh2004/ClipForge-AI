from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from clipforge.common import logging as logging_mod
from clipforge.common.ports import QueueBroker

logger = logging_mod.get_logger(__name__)

# Serverless/free-tier Redis (Upstash-style) sleeps when idle; the first
# connection after sleep can fail. Recreate the broker's client and retry a
# couple of times before giving up, so a cold Redis doesn't 500 the request.
_ENQUEUE_RETRIES = 3


class DramatiqBroker(QueueBroker):
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._broker = self._build_broker()

    def _build_broker(self) -> dramatiq.Broker:
        broker: dramatiq.Broker = RedisBroker(url=self._redis_url)  # type: ignore[no-untyped-call]
        dramatiq.set_broker(broker)
        return broker

    def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        queue: str = "default",
        delay: int = 0,
    ) -> str:
        message: dramatiq.Message[Any] = dramatiq.Message(
            queue_name=queue,
            actor_name=task_name,
            args=(),
            kwargs={"payload": payload},
            options={},
        )
        last_error: Exception | None = None
        for attempt in range(_ENQUEUE_RETRIES):
            try:
                if delay > 0:
                    self._broker.enqueue(message, delay=delay)
                else:
                    self._broker.enqueue(message)
                return message.message_id
            except Exception as exc:  # pragma: no cover - network path
                last_error = exc
                logger.warning(
                    "enqueue_retry",
                    task=task_name,
                    queue=queue,
                    attempt=attempt + 1,
                    error=str(exc)[:200],
                )
                # The pooled connection is stale (serverless Redis slept);
                # rebuild the broker so the next attempt uses a fresh client.
                self._broker = self._build_broker()
        assert last_error is not None
        raise last_error
