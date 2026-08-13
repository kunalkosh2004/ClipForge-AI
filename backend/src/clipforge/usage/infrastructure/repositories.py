from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.common.ports import AIModelUsage
from clipforge.db import models as orm
from clipforge.usage.domain.entities import AIModelUsageRecord
from clipforge.usage.domain.ports import AIModelUsageRepository


class SQLAlchemyAIModelUsageRepository(AIModelUsageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, usage: AIModelUsageRecord) -> None:
        row = orm.AIModelUsage(
            id=usage.id,
            date=usage.date,
            model=usage.model,
            key_label=usage.key,
            operation=usage.operation,
            prompt_tokens=usage.prompt_tokens,
            response_tokens=usage.response_tokens,
            total_tokens=usage.total_tokens,
            video_id=usage.video_id,
        )
        self._session.add(row)
        await self._session.flush()

    async def usage_for_day(self, day: date) -> list[AIModelUsageRecord]:
        stmt = select(orm.AIModelUsage).where(orm.AIModelUsage.date == day)
        rows = (await self._session.scalars(stmt)).all()
        return [_usage_to_domain(r) for r in rows]


class SessionAIModelUsageRecorder:
    """Adapts an ``AIModelUsage`` provider callback into persisted rows.

    Each call opens and commits its own session so the recorder is safe to
    invoke from the long-lived provider regardless of the caller's transaction.
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, usage: AIModelUsage) -> None:
        async with self._session_factory() as session:
            await SQLAlchemyAIModelUsageRepository(session).record(
                AIModelUsageRecord(
                    date=date.today(),
                    model=usage.model,
                    key=usage.key,
                    operation=usage.operation,
                    prompt_tokens=usage.prompt_tokens,
                    response_tokens=usage.response_tokens,
                    total_tokens=usage.total_tokens,
                )
            )
            await session.commit()


def _usage_to_domain(row: orm.AIModelUsage) -> AIModelUsageRecord:
    return AIModelUsageRecord(
        id=row.id,
        date=row.date,
        model=row.model,
        key=row.key_label,
        operation=row.operation,
        prompt_tokens=row.prompt_tokens,
        response_tokens=row.response_tokens,
        total_tokens=row.total_tokens,
        video_id=row.video_id,
        created_at=row.created_at,
    )
