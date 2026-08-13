import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.analysis.domain.entities import AnalysisResultRecord, TranscriptRecord
from clipforge.analysis.domain.ports import AnalysisResultRepository, TranscriptRepository
from clipforge.db import models as orm


class SQLAlchemyTranscriptRepository(TranscriptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_video_id(self, video_id: uuid.UUID) -> TranscriptRecord | None:
        stmt = select(orm.Transcript).where(orm.Transcript.video_id == video_id)
        row = await self._session.scalar(stmt)
        return _transcript_to_domain(row) if row is not None else None

    async def create(self, transcript: TranscriptRecord) -> TranscriptRecord:
        row = orm.Transcript(
            id=transcript.id,
            video_id=transcript.video_id,
            language=transcript.language,
            segments=transcript.segments,
            words=transcript.words,
        )
        self._session.add(row)
        await self._session.flush()
        return _transcript_to_domain(row)


class SQLAlchemyAnalysisResultRepository(AnalysisResultRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_video_id(self, video_id: uuid.UUID) -> AnalysisResultRecord | None:
        stmt = select(orm.AnalysisResult).where(orm.AnalysisResult.video_id == video_id)
        row = await self._session.scalar(stmt)
        return _analysis_result_to_domain(row) if row is not None else None

    async def create(self, result: AnalysisResultRecord) -> AnalysisResultRecord:
        row = orm.AnalysisResult(
            id=result.id,
            video_id=result.video_id,
            understanding=result.understanding,
            editing_plan=result.editing_plan,
            editing_blueprint=result.editing_blueprint,
            ai_model=result.ai_model,
            ai_cost_cents=result.ai_cost_cents,
        )
        self._session.add(row)
        await self._session.flush()
        return _analysis_result_to_domain(row)


def _transcript_to_domain(row: orm.Transcript) -> TranscriptRecord:
    return TranscriptRecord(
        id=row.id,
        video_id=row.video_id,
        language=row.language,
        segments=row.segments or [],
        words=row.words or [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _analysis_result_to_domain(row: orm.AnalysisResult) -> AnalysisResultRecord:
    return AnalysisResultRecord(
        id=row.id,
        video_id=row.video_id,
        understanding=row.understanding,
        editing_plan=row.editing_plan,
        editing_blueprint=row.editing_blueprint,
        ai_model=row.ai_model,
        ai_cost_cents=row.ai_cost_cents,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
