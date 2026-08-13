import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.common.pagination import PageRequest, PageResult
from clipforge.db import models as orm
from clipforge.processing.domain.entities import Job
from clipforge.processing.domain.ports import JobRepository


class SQLAlchemyJobRepository(JobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_dedupe_key(self, dedupe_key: str) -> Job | None:
        row = await self._session.scalar(select(orm.Job).where(orm.Job.dedupe_key == dedupe_key))
        return _job_to_domain(row) if row is not None else None

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        row = await self._session.get(orm.Job, job_id)
        return _job_to_domain(row) if row is not None else None

    async def list_all(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        video_id: uuid.UUID | None = None,
        page: PageRequest | None = None,
    ) -> PageResult[Job]:
        page = page or PageRequest()
        filters = []
        if status is not None:
            filters.append(orm.Job.status == orm.JobStatus(status))
        if job_type is not None:
            filters.append(orm.Job.type == orm.JobType(job_type))
        if video_id is not None:
            filters.append(orm.Job.video_id == video_id)

        base = select(orm.Job).where(*filters)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.scalar(count_stmt)) or 0

        stmt = base.order_by(orm.Job.created_at.desc()).limit(page.limit).offset(page.offset)
        rows = (await self._session.scalars(stmt)).all()
        return PageResult(
            items=[_job_to_domain(row) for row in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def create(self, job: Job) -> Job:
        row = orm.Job(
            id=job.id,
            video_id=job.video_id,
            type=orm.JobType(job.type),
            status=orm.JobStatus(job.status),
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            dedupe_key=job.dedupe_key,
            last_error=job.last_error,
        )
        self._session.add(row)
        await self._session.flush()
        return _job_to_domain(row)

    async def mark_running(self, job_id: uuid.UUID) -> Job | None:
        row = await self._session.get(orm.Job, job_id)
        if row is None:
            return None
        row.status = orm.JobStatus.RUNNING
        row.attempts += 1
        row.last_error = None
        await self._session.flush()
        await self._session.refresh(row)
        return _job_to_domain(row)

    async def mark_succeeded(self, job_id: uuid.UUID) -> Job | None:
        row = await self._session.get(orm.Job, job_id)
        if row is None:
            return None
        row.status = orm.JobStatus.SUCCEEDED
        row.last_error = None
        await self._session.flush()
        await self._session.refresh(row)
        return _job_to_domain(row)

    async def mark_failed(self, job_id: uuid.UUID, error: str) -> Job | None:
        row = await self._session.get(orm.Job, job_id)
        if row is None:
            return None
        row.status = orm.JobStatus.FAILED
        row.last_error = error
        await self._session.flush()
        await self._session.refresh(row)
        return _job_to_domain(row)


def _job_to_domain(row: orm.Job) -> Job:
    return Job(
        id=row.id,
        video_id=row.video_id,
        type=row.type.value,
        status=row.status.value,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        dedupe_key=row.dedupe_key,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
