from abc import ABC, abstractmethod
from typing import Any


class QueueBroker(ABC):
    @abstractmethod
    def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        queue: str = "default",
        delay: int = 0,
    ) -> str:
        """Dispatch a task and return its message id. delay is in milliseconds."""
