from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from clipforge.common.ports import QueueBroker


class DramatiqBroker(QueueBroker):
    def __init__(self, redis_url: str) -> None:
        self._broker: dramatiq.Broker = RedisBroker(url=redis_url)  # type: ignore[no-untyped-call]
        dramatiq.set_broker(self._broker)

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
        if delay > 0:
            self._broker.enqueue(message, delay=delay)
        else:
            self._broker.enqueue(message)
        return message.message_id
