import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.common.pagination import PageRequest, PageResult
from clipforge.db import models as orm
from clipforge.videos.domain.entities import Project, Video
from clipforge.videos.domain.ports import ProjectRepository, VideoRepository


class SQLAlchemyProjectRepository(ProjectRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        row = await self._session.get(orm.Project, project_id)
        return _project_to_domain(row) if row is not None else None

    async def create(self, project: Project) -> Project:
        row = orm.Project(
            id=project.id,
            owner_id=project.owner_id,
            name=project.name,
            status=orm.ProjectStatus(project.status),
        )
        self._session.add(row)
        await self._session.flush()
        return _project_to_domain(row)

    async def list_for_owner(
        self, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Project]:
        page = page or PageRequest()
        count_stmt = (
            select(func.count())
            .select_from(orm.Project)
            .where(orm.Project.owner_id == owner_id)
        )
        total = (await self._session.scalar(count_stmt)) or 0

        stmt = (
            select(orm.Project)
            .where(orm.Project.owner_id == owner_id)
            .order_by(orm.Project.created_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        )
        rows = (await self._session.scalars(stmt)).all()
        return PageResult(
            items=[_project_to_domain(row) for row in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def delete(self, project_id: uuid.UUID) -> bool:
        row = await self._session.get(orm.Project, project_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True


class SQLAlchemyVideoRepository(VideoRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned(self, video_id: uuid.UUID, owner_id: uuid.UUID) -> Video | None:
        stmt = (
            select(orm.Video)
            .join(orm.Project, orm.Video.project_id == orm.Project.id)
            .where(orm.Video.id == video_id, orm.Project.owner_id == owner_id)
        )
        row = await self._session.scalar(stmt)
        return _video_to_domain(row) if row is not None else None

    async def get_by_id(self, video_id: uuid.UUID) -> Video | None:
        row = await self._session.get(orm.Video, video_id)
        return _video_to_domain(row) if row is not None else None

    async def create(self, video: Video) -> Video:
        row = orm.Video(
            id=video.id,
            project_id=video.project_id,
            original_filename=video.original_filename,
            source_url=video.source_url,
            storage_key=video.storage_key,
            content_type=video.content_type,
            size_bytes=video.size_bytes,
            checksum=video.checksum,
            editing_style=video.editing_style,
            status=orm.VideoStatus(video.status),
        )
        self._session.add(row)
        await self._session.flush()
        return _video_to_domain(row)

    async def update_status(self, video_id: uuid.UUID, status: str) -> Video | None:
        row = await self._session.get(orm.Video, video_id)
        if row is None:
            return None
        row.status = orm.VideoStatus(status)
        await self._session.flush()
        await self._session.refresh(row)
        return _video_to_domain(row)

    async def update_editing_style(
        self, video_id: uuid.UUID, editing_style: str | None
    ) -> Video | None:
        row = await self._session.get(orm.Video, video_id)
        if row is None:
            return None
        row.editing_style = editing_style
        await self._session.flush()
        await self._session.refresh(row)
        return _video_to_domain(row)

    async def update_metadata(
        self,
        video_id: uuid.UUID,
        *,
        checksum: str,
        size_bytes: int,
        duration_seconds: float | None,
        metadata_json: dict[str, Any],
        status: str,
    ) -> Video | None:
        row = await self._session.get(orm.Video, video_id)
        if row is None:
            return None
        row.checksum = checksum
        row.size_bytes = size_bytes
        row.duration_seconds = duration_seconds
        row.metadata_json = metadata_json
        row.status = orm.VideoStatus(status)
        await self._session.flush()
        await self._session.refresh(row)
        return _video_to_domain(row)

    async def update_imported(
        self,
        video_id: uuid.UUID,
        *,
        original_filename: str,
        checksum: str,
        size_bytes: int,
        duration_seconds: float | None,
        metadata_json: dict[str, Any],
        status: str,
    ) -> Video | None:
        row = await self._session.get(orm.Video, video_id)
        if row is None:
            return None
        row.original_filename = original_filename
        row.checksum = checksum
        row.size_bytes = size_bytes
        row.duration_seconds = duration_seconds
        row.metadata_json = metadata_json
        row.status = orm.VideoStatus(status)
        await self._session.flush()
        await self._session.refresh(row)
        return _video_to_domain(row)

    async def list_for_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, page: PageRequest | None = None
    ) -> PageResult[Video]:
        page = page or PageRequest()
        base = (
            select(orm.Video)
            .join(orm.Project, orm.Video.project_id == orm.Project.id)
            .where(orm.Video.project_id == project_id, orm.Project.owner_id == owner_id)
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.scalar(count_stmt)) or 0

        stmt = base.order_by(orm.Video.created_at.desc()).limit(page.limit).offset(page.offset)
        rows = (await self._session.scalars(stmt)).all()
        return PageResult(
            items=[_video_to_domain(row) for row in rows],
            total=total,
            limit=page.limit,
            offset=page.offset,
        )

    async def delete(self, video_id: uuid.UUID) -> bool:
        row = await self._session.get(orm.Video, video_id)
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True


def _project_to_domain(row: orm.Project) -> Project:
    return Project(
        id=row.id,
        owner_id=row.owner_id,
        name=row.name,
        status=row.status.value,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _video_to_domain(row: orm.Video) -> Video:
    return Video(
        id=row.id,
        project_id=row.project_id,
        original_filename=row.original_filename,
        source_url=row.source_url,
        storage_key=row.storage_key,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        checksum=row.checksum,
        duration_seconds=row.duration_seconds,
        editing_style=row.editing_style,
        metadata_json=row.metadata_json,
        status=row.status.value,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
