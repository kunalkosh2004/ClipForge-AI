import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.db import models as orm
from clipforge.workflow.domain.entities import WorkflowNode
from clipforge.workflow.domain.ports import WorkflowNodeRepository


class SQLAlchemyWorkflowNodeRepository(WorkflowNodeRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, node: WorkflowNode) -> WorkflowNode:
        row = orm.WorkflowNode(
            id=node.id,
            video_id=node.video_id,
            kind=node.kind,
            status=orm.WorkflowNodeStatus(node.status),
            attempts=node.attempts,
            max_attempts=node.max_attempts,
            depends_on=list(node.depends_on),
            queue=node.queue,
            started_at=node.started_at,
            completed_at=node.completed_at,
            error=node.error,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get(self, video_id: uuid.UUID, kind: str) -> WorkflowNode | None:
        stmt = select(orm.WorkflowNode).where(
            orm.WorkflowNode.video_id == video_id,
            orm.WorkflowNode.kind == kind,
        )
        row = await self._session.scalar(stmt)
        return _to_domain(row) if row is not None else None

    async def list_for_video(self, video_id: uuid.UUID) -> list[WorkflowNode]:
        stmt = (
            select(orm.WorkflowNode)
            .where(orm.WorkflowNode.video_id == video_id)
            .order_by(orm.WorkflowNode.kind.asc())
        )
        rows = (await self._session.scalars(stmt)).all()
        return [_to_domain(row) for row in rows]

    async def mark_running(self, node_id: uuid.UUID) -> WorkflowNode | None:
        return await self._update(
            node_id,
            status=orm.WorkflowNodeStatus.RUNNING,
            attempts=orm.WorkflowNode.attempts + 1,
            started_at=datetime.now(UTC),
            error=None,
        )

    async def mark_succeeded(self, node_id: uuid.UUID) -> WorkflowNode | None:
        return await self._update(
            node_id,
            status=orm.WorkflowNodeStatus.SUCCEEDED,
            completed_at=datetime.now(UTC),
        )

    async def mark_failed(self, node_id: uuid.UUID, error: str) -> WorkflowNode | None:
        return await self._update(
            node_id,
            status=orm.WorkflowNodeStatus.FAILED,
            completed_at=datetime.now(UTC),
            error=error[:2000],
        )

    async def mark_skipped(self, node_id: uuid.UUID) -> WorkflowNode | None:
        return await self._update(
            node_id,
            status=orm.WorkflowNodeStatus.SKIPPED,
            completed_at=datetime.now(UTC),
        )

    async def reset_stale(
        self, video_id: uuid.UUID, max_started_age_seconds: int
    ) -> list[WorkflowNode]:
        rows = await self._session.scalars(
            select(orm.WorkflowNode)
            .where(
                orm.WorkflowNode.video_id == video_id,
                orm.WorkflowNode.status == orm.WorkflowNodeStatus.RUNNING,
            )
            .order_by(orm.WorkflowNode.kind.asc())
        )
        stale: list[WorkflowNode] = []
        now = datetime.now(UTC)
        for row in rows.all():
            started = row.started_at
            if started is None:
                continue
            age = (now - started.replace(tzinfo=UTC)).total_seconds()
            if age <= max_started_age_seconds:
                continue
            row.status = orm.WorkflowNodeStatus.WAITING
            row.started_at = None
            stale.append(_to_domain(row))
        await self._session.flush()
        return stale

    async def list_stale_video_ids(
        self, max_started_age_seconds: int
    ) -> list[uuid.UUID]:
        """Distinct videos with at least one running node older than the
        threshold — used by the boot-time recovery sweep."""
        stmt = (
            select(orm.WorkflowNode.video_id, func.min(orm.WorkflowNode.started_at))
            .where(
                orm.WorkflowNode.status == orm.WorkflowNodeStatus.RUNNING,
                orm.WorkflowNode.started_at.is_not(None),
            )
            .group_by(orm.WorkflowNode.video_id)
        )
        rows = (await self._session.execute(stmt)).all()
        cutoff = datetime.now(UTC) - timedelta(seconds=max_started_age_seconds)
        stale: list[uuid.UUID] = []
        for video_id, oldest_started in rows:
            if oldest_started is None:
                continue
            if oldest_started.replace(tzinfo=UTC) < cutoff:
                stale.append(uuid.UUID(str(video_id)))
        return stale

    async def _update(self, node_id: uuid.UUID, **fields: object) -> WorkflowNode | None:
        row = await self._session.get(orm.WorkflowNode, node_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        await self._session.flush()
        # Refresh the (possibly expired) row async-safely — SQL-expression
        # assignments like `attempts + 1` are expired after flush and cannot be
        # read without an active greenlet.
        await self._session.refresh(row)
        return _to_domain(row)


def _to_domain(row: orm.WorkflowNode) -> WorkflowNode:
    return WorkflowNode(
        id=row.id,
        video_id=row.video_id,
        kind=row.kind,
        depends_on=tuple(row.depends_on or []),
        queue=row.queue,
        max_attempts=row.max_attempts,
        status=row.status.value,
        attempts=row.attempts,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error=row.error,
        created_at=row.created_at,
    )
