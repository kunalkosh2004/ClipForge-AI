from abc import ABC, abstractmethod
from datetime import date

from clipforge.usage.domain.entities import AIModelUsageRecord


class AIModelUsageRepository(ABC):
    @abstractmethod
    async def record(self, usage: AIModelUsageRecord) -> None:
        """Persist a single provider call's token usage."""

    @abstractmethod
    async def usage_for_day(self, day: date) -> list[AIModelUsageRecord]:
        """All usage rows recorded on the given calendar day."""
