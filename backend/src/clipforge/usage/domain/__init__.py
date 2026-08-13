"""AI model usage tracking — token consumption for the quota UI."""

from clipforge.usage.domain.entities import AIModelUsageRecord
from clipforge.usage.domain.ports import AIModelUsageRepository

__all__ = ["AIModelUsageRecord", "AIModelUsageRepository"]
