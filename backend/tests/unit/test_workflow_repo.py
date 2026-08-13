import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from clipforge.db import models as orm
from clipforge.workflow.domain.entities import (
    NODE_FAILED,
    NODE_RUNNING,
    NODE_SUCCEEDED,
    NODE_WAITING,
    WorkflowNode,
)
from clipforge.workflow.infrastructure.repositories import SQLAlchemyWorkflowNodeRepository


def _node(video_id: uuid.UUID, kind: str = "metadata") -> WorkflowNode:
    return WorkflowNode(
        id=uuid.uuid4(),
        video_id=video_id,
        kind=kind,
        depends_on=(),
        queue="media",
        max_attempts=5,
    )


@pytest.mark.asyncio
async def test_mark_running_increments_attempts(session: AsyncSession) -> None:
    repo = SQLAlchemyWorkflowNodeRepository(session)
    video_id = uuid.uuid4()
    created = await repo.create(_node(video_id))
    assert created.status == NODE_WAITING
    assert created.attempts == 0

    running = await repo.mark_running(created.id)
    assert running is not None
    assert running.status == NODE_RUNNING
    assert running.attempts == 1
    assert running.started_at is not None

    succeeded = await repo.mark_succeeded(created.id)
    assert succeeded is not None
    assert succeeded.status == NODE_SUCCEEDED
    assert succeeded.completed_at is not None


@pytest.mark.asyncio
async def test_mark_failed_records_error(session: AsyncSession) -> None:
    repo = SQLAlchemyWorkflowNodeRepository(session)
    video_id = uuid.uuid4()
    created = await repo.create(_node(video_id))
    failed = await repo.mark_failed(created.id, "boom")
    assert failed is not None
    assert failed.status == NODE_FAILED
    assert failed.error == "boom"


@pytest.mark.asyncio
async def test_reset_stale_returns_old_running_only(session: AsyncSession) -> None:
    repo = SQLAlchemyWorkflowNodeRepository(session)
    video_id = uuid.uuid4()
    old = await repo.create(_node(video_id, kind="metadata"))
    old = await repo.mark_running(old.id)
    assert old is not None
    await session.execute(
        orm.WorkflowNode.__table__.update()
        .where(orm.WorkflowNode.id == old.id)
        .values(started_at=datetime.now(UTC) - timedelta(seconds=600))
    )
    await session.commit()

    stale = await repo.reset_stale(video_id, max_started_age_seconds=1)
    assert len(stale) == 1
    assert stale[0].kind == "metadata"
    assert stale[0].status == NODE_WAITING
    assert stale[0].started_at is None


@pytest.mark.asyncio
async def test_reset_stale_keeps_fresh(session: AsyncSession) -> None:
    repo = SQLAlchemyWorkflowNodeRepository(session)
    video_id = uuid.uuid4()
    fresh = await repo.create(_node(video_id, kind="metadata"))
    fresh = await repo.mark_running(fresh.id)
    assert fresh is not None
    await session.execute(
        orm.WorkflowNode.__table__.update()
        .where(orm.WorkflowNode.id == fresh.id)
        .values(started_at=datetime.now(UTC))
    )
    await session.commit()

    stale = await repo.reset_stale(video_id, max_started_age_seconds=3600)
    assert stale == []


@pytest.mark.asyncio
async def test_duplicate_kind_violates_unique_constraint(session: AsyncSession) -> None:
    repo = SQLAlchemyWorkflowNodeRepository(session)
    video_id = uuid.uuid4()
    await repo.create(_node(video_id, kind="metadata"))
    await session.commit()
    with pytest.raises(IntegrityError):
        await repo.create(_node(video_id, kind="metadata"))
        await session.commit()
    await session.rollback()
