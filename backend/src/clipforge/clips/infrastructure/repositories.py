import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.clips.domain.entities import Clip
from clipforge.clips.domain.ports import ClipRepository
from clipforge.common.pagination import PageRequest, PageResult
from clipforge.db import models as orm


class SQLAlchemyClipRepository(ClipRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, clip_id: uuid.UUID) -> Clip | None:
        row = await self._session.get(orm.Clip, clip_id)
        return _clip_to_domain(row) if row is not None else None

    async def list_for_video(
        self, video_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        page = page or PageRequest()
        base = select(orm.Clip).where(orm.Clip.video_id == video_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.scalar(count_stmt)) or 0

        stmt = base.order_by(orm.Clip.start_seconds).limit(page.limit).offset(page.offset)
        rows = (await self._session.scalars(stmt)).all()
        return PageResult(
            items=[_clip_to_domain(row) for row in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def list_for_project(
        self, project_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Clip]:
        page = page or PageRequest()
        base = select(orm.Clip).where(orm.Clip.project_id == project_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.scalar(count_stmt)) or 0

        stmt = base.order_by(orm.Clip.created_at.desc()).limit(page.limit).offset(page.offset)
        rows = (await self._session.scalars(stmt)).all()
        return PageResult(
            items=[_clip_to_domain(row) for row in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def count_for_video(self, video_id: uuid.UUID) -> int:
        count_stmt = (
            select(func.count()).select_from(orm.Clip).where(orm.Clip.video_id == video_id)
        )
        return (await self._session.scalar(count_stmt)) or 0

    async def create(self, clip: Clip) -> Clip:
        row = orm.Clip(
            id=clip.id,
            video_id=clip.video_id,
            project_id=clip.project_id,
            title=clip.title,
            start_seconds=clip.start_seconds,
            end_seconds=clip.end_seconds,
            duration_seconds=clip.duration_seconds,
            storage_key=clip.storage_key,
            render_storage_key=clip.render_storage_key,
            thumbnail_storage_key=clip.thumbnail_storage_key,
            editing_plan_json=clip.editing_plan_json,
            format=clip.format,
            status=orm.ClipStatus(clip.status),
            rendered=clip.rendered,
        )
        self._session.add(row)
        await self._session.flush()
        return _clip_to_domain(row)

    async def update_status(self, clip_id: uuid.UUID, status: str) -> Clip | None:
        row = await self._session.get(orm.Clip, clip_id)
        if row is None:
            return None
        row.status = orm.ClipStatus(status)
        await self._session.flush()
        await self._session.refresh(row)
        return _clip_to_domain(row)

    async def update_storage(
        self, clip_id: uuid.UUID, storage_key: str, thumbnail_storage_key: str | None = None
    ) -> Clip | None:
        row = await self._session.get(orm.Clip, clip_id)
        if row is None:
            return None
        row.storage_key = storage_key
        row.status = orm.ClipStatus.READY
        if thumbnail_storage_key is not None:
            row.thumbnail_storage_key = thumbnail_storage_key
        await self._session.flush()
        await self._session.refresh(row)
        return _clip_to_domain(row)

    async def update_render(
        self, clip_id: uuid.UUID, render_storage_key: str, thumbnail_storage_key: str | None = None
    ) -> Clip | None:
        row = await self._session.get(orm.Clip, clip_id)
        if row is None:
            return None
        row.render_storage_key = render_storage_key
        row.rendered = True
        row.status = orm.ClipStatus.READY
        if thumbnail_storage_key is not None:
            row.thumbnail_storage_key = thumbnail_storage_key
        await self._session.flush()
        await self._session.refresh(row)
        return _clip_to_domain(row)

    async def delete(self, clip_id: uuid.UUID) -> bool:
        row = await self._session.get(orm.Clip, clip_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True


def _clip_to_domain(row: orm.Clip) -> Clip:
    return Clip(
        id=row.id,
        video_id=row.video_id,
        project_id=row.project_id,
        title=row.title,
        start_seconds=row.start_seconds,
        end_seconds=row.end_seconds,
        duration_seconds=row.duration_seconds,
        storage_key=row.storage_key,
        render_storage_key=row.render_storage_key,
        thumbnail_storage_key=row.thumbnail_storage_key,
        editing_plan_json=row.editing_plan_json,
        format=row.format,
        status=row.status.value,
        rendered=row.rendered,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
