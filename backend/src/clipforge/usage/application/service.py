from datetime import date

from clipforge.config import Settings
from clipforge.usage.application.schemas import (
    AIModelUsageSummary,
    AIUsageSummaryResponse,
)
from clipforge.usage.domain.ports import AIModelUsageRepository


class AIUsageService:
    def __init__(
        self,
        usage: AIModelUsageRepository,
        settings: Settings,
    ) -> None:
        self._usage = usage
        self._settings = settings

    async def summary_for_today(self) -> AIUsageSummaryResponse:
        day = date.today()
        rows = await self._usage.usage_for_day(day)
        token_limit = max(0, self._settings.gemini_daily_token_limit)
        request_limit = max(0, self._settings.gemini_daily_request_limit)

        per_key: dict[str, dict[str, int | str]] = {}
        for row in rows:
            key = row.key or "primary"
            bucket = per_key.setdefault(
                key,
                {"requests": 0, "tokens": 0, "model": row.model},
            )
            bucket["requests"] = int(bucket["requests"]) + 1
            bucket["tokens"] = int(bucket["tokens"]) + row.total_tokens

        keys: list[AIModelUsageSummary] = []
        for key, bucket in sorted(per_key.items()):
            requests = int(bucket["requests"])
            tokens = int(bucket["tokens"])
            keys.append(
                AIModelUsageSummary(
                    key=key,
                    model=str(bucket["model"]),
                    requests=requests,
                    request_limit=request_limit,
                    requests_remaining=max(0, request_limit - requests),
                    tokens_used=tokens,
                    token_limit=token_limit,
                    tokens_remaining=max(0, token_limit - tokens),
                )
            )

        tokens_used = sum(int(b["tokens"]) for b in per_key.values())
        requests = sum(int(b["requests"]) for b in per_key.values())
        return AIUsageSummaryResponse(
            date=day.isoformat(),
            keys=keys,
            tokens_used=tokens_used,
            token_limit=token_limit,
            tokens_remaining=max(0, token_limit - tokens_used),
            requests=requests,
            request_limit=request_limit,
            requests_remaining=max(0, request_limit - requests),
        )
