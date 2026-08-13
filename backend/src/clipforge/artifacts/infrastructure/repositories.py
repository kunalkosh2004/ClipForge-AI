import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.artifacts.domain.entities import Artifact
from clipforge.artifacts.domain.ports import ArtifactRepository
from clipforge.db import models as orm


class SQLAlchemyArtifactRepository(ArtifactRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, artifact: Artifact) -> Artifact:
        row = orm.Artifact(
            id=artifact.id,
            video_id=artifact.video_id,
            kind=artifact.kind,
            version=artifact.version,
            storage_key=artifact.storage_key,
            checksum=artifact.checksum,
            size_bytes=artifact.size_bytes,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get_latest(self, video_id: uuid.UUID, kind: str) -> Artifact | None:
        stmt = (
            select(orm.Artifact)
            .where(orm.Artifact.video_id == video_id, orm.Artifact.kind == kind)
            .order_by(orm.Artifact.created_at.desc())
            .limit(1)
        )
        row = await self._session.scalar(stmt)
        return _to_domain(row) if row is not None else None

    async def list_for_video(self, video_id: uuid.UUID) -> list[Artifact]:
        stmt = (
            select(orm.Artifact)
            .where(orm.Artifact.video_id == video_id)
            .order_by(orm.Artifact.kind.asc())
        )
        rows = (await self._session.scalars(stmt)).all()
        return [_to_domain(row) for row in rows]

    async def delete_for_video(self, video_id: uuid.UUID) -> int:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(orm.Artifact).where(orm.Artifact.video_id == video_id)
            ),
        )
        return result.rowcount or 0


def _to_domain(row: orm.Artifact) -> Artifact:
    return Artifact(
        id=row.id,
        video_id=row.video_id,
        kind=row.kind,
        version=row.version,
        storage_key=row.storage_key,
        checksum=row.checksum,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )
