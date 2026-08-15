import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from clipforge.workflow.application.engine import WorkflowEngine
from clipforge.workflow.domain.entities import (
    NODE_FAILED,
    NODE_RUNNING,
    NODE_SKIPPED,
    NODE_SUCCEEDED,
    NODE_WAITING,
    WorkflowNode,
)
from clipforge.workflow.domain.graph import WORKFLOW_GRAPH
from clipforge.workflow.domain.ports import WorkflowNodeRepository


class FakeNodeRepo(WorkflowNodeRepository):
    def __init__(self) -> None:
        self._nodes: dict[tuple[uuid.UUID, str], WorkflowNode] = {}

    def _by_id(self, node_id: uuid.UUID) -> WorkflowNode | None:
        for node in self._nodes.values():
            if node.id == node_id:
                return node
        return None

    def _replace(self, node: WorkflowNode, updated: WorkflowNode) -> None:
        for key in list(self._nodes):
            if self._nodes[key].id == node.id:
                self._nodes[key] = updated
                return
        self._nodes[(node.video_id, node.kind)] = updated

    async def create(self, node: WorkflowNode) -> WorkflowNode:
        self._nodes[(node.video_id, node.kind)] = node
        return node

    async def get(self, video_id: uuid.UUID, kind: str) -> WorkflowNode | None:
        return self._nodes.get((video_id, kind))

    async def list_for_video(self, video_id: uuid.UUID) -> list[WorkflowNode]:
        return [n for (v, _), n in self._nodes.items() if v == video_id]

    async def mark_running(self, node_id: uuid.UUID) -> WorkflowNode | None:
        node = self._by_id(node_id)
        if node is None:
            return None
        updated = replace(
            node,
            status=NODE_RUNNING,
            attempts=node.attempts + 1,
            started_at=datetime.now(UTC),
            error=None,
        )
        self._replace(node, updated)
        return updated

    async def mark_succeeded(self, node_id: uuid.UUID) -> WorkflowNode | None:
        return self._transition(node_id, NODE_SUCCEEDED)

    async def mark_failed(self, node_id: uuid.UUID, error: str) -> WorkflowNode | None:
        node = self._by_id(node_id)
        if node is None:
            return None
        updated = replace(node, status=NODE_FAILED, error=error)
        self._replace(node, updated)
        return updated

    async def mark_skipped(self, node_id: uuid.UUID) -> WorkflowNode | None:
        return self._transition(node_id, NODE_SKIPPED)

    async def reset_stale(
        self, video_id: uuid.UUID, max_started_age_seconds: int
    ) -> list[WorkflowNode]:
        now = datetime.now(UTC)
        stale: list[WorkflowNode] = []
        for node in list(self._nodes.values()):
            if node.video_id != video_id or node.status != NODE_RUNNING:
                continue
            if node.started_at is None:
                continue
            age = (now - node.started_at).total_seconds()
            if age <= max_started_age_seconds:
                continue
            updated = replace(node, status=NODE_WAITING, started_at=None)
            self._replace(node, updated)
            stale.append(updated)
        return stale

    async def list_stale_video_ids(
        self, max_started_age_seconds: int
    ) -> list[uuid.UUID]:
        now = datetime.now(UTC)
        stale: set[uuid.UUID] = set()
        for node in self._nodes.values():
            if node.status != NODE_RUNNING or node.started_at is None:
                continue
            if (now - node.started_at).total_seconds() > max_started_age_seconds:
                stale.add(node.video_id)
        return list(stale)

    def _transition(self, node_id: uuid.UUID, status: str) -> WorkflowNode | None:
        node = self._by_id(node_id)
        if node is None:
            return None
        updated = replace(node, status=status, completed_at=datetime.now(UTC))
        self._replace(node, updated)
        return updated


class FakeQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        *,
        queue: str = "default",
        delay: int = 0,
    ) -> str:
        self.messages.append(
            {"task": task_name, "payload": payload, "queue": queue, "delay": delay}
        )
        return "msg"

    def clear(self) -> None:
        self.messages.clear()

    def kinds(self) -> list[str]:
        return [m["payload"]["kind"] for m in self.messages]


def _engine() -> tuple[WorkflowEngine, FakeNodeRepo, FakeQueue]:
    nodes = FakeNodeRepo()
    queue = FakeQueue()
    return WorkflowEngine(nodes, queue), nodes, queue


@pytest.mark.asyncio
async def test_ensure_creates_full_graph_and_is_idempotent() -> None:
    engine, nodes, _ = _engine()
    video_id = uuid.uuid4()

    await engine.ensure(video_id)
    assert {n.kind for n in await nodes.list_for_video(video_id)} == {
        spec.kind for spec in WORKFLOW_GRAPH
    }

    await engine.ensure(video_id)
    assert len(await nodes.list_for_video(video_id)) == len(WORKFLOW_GRAPH)


@pytest.mark.asyncio
async def test_start_enqueues_only_root_nodes() -> None:
    engine, _, queue = _engine()
    video_id = uuid.uuid4()

    await engine.start(video_id)
    assert queue.kinds() == ["metadata"]
    assert queue.messages[0]["queue"] == "media"


@pytest.mark.asyncio
async def test_advance_fans_out_once_dependencies_succeed() -> None:
    engine, _, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)
    queue.clear()

    # metadata succeeds -> scene, motion, beat become ready
    await engine.succeed(video_id, "metadata")
    ready = await engine.advance(video_id)
    assert sorted(n.kind for n in ready) == ["beat", "motion", "scene"]
    assert sorted(queue.kinds()) == ["beat", "motion", "scene"]


@pytest.mark.asyncio
async def test_children_not_enqueued_while_dependency_pending() -> None:
    engine, nodes, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)
    queue.clear()

    node = await nodes.get(video_id, "scene")
    # simulate a stray advance before metadata completes
    await engine.advance(video_id)
    assert queue.kinds() == []
    assert node.status == NODE_WAITING


@pytest.mark.asyncio
async def test_advance_claims_atomically_no_double_enqueue() -> None:
    engine, _, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)
    queue.clear()
    await engine.succeed(video_id, "metadata")

    await engine.advance(video_id)
    await engine.advance(video_id)  # second advance must not re-enqueue
    assert sorted(queue.kinds()) == ["beat", "motion", "scene"]


@pytest.mark.asyncio
async def test_retry_resets_and_re_enqueues_with_backoff() -> None:
    engine, _, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)
    queue.clear()

    reenqueued = await engine.retry(video_id, "metadata", "boom")
    assert reenqueued is True
    assert queue.kinds() == ["metadata"]
    assert queue.messages[0]["delay"] == 1000


@pytest.mark.asyncio
async def test_retry_fails_permanently_when_attempts_exhausted() -> None:
    engine, nodes, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)
    queue.clear()

    # exhaust the attempt budget
    exhausted = False
    for _ in range(10):
        if not await engine.retry(video_id, "metadata", "boom"):
            exhausted = True
            break
        queue.clear()
    assert exhausted
    node = await nodes.get(video_id, "metadata")
    assert node.status == NODE_FAILED


@pytest.mark.asyncio
async def test_reconcile_recovers_stale_running_nodes() -> None:
    engine, nodes, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)

    # make metadata stale by faking an old started_at
    node = await nodes.get(video_id, "metadata")
    stale = replace(node, status=NODE_RUNNING, started_at=datetime.now(UTC) - timedelta(hours=1))
    await nodes.create(stale)
    queue.clear()

    await engine.reconcile(video_id, stale_seconds=600)
    # metadata reset to waiting then re-enqueued
    assert queue.kinds() == ["metadata"]
    node = await nodes.get(video_id, "metadata")
    assert node.status == NODE_RUNNING  # claimed again by advance
    assert node.attempts >= 2


@pytest.mark.asyncio
async def test_reconcile_leaves_fresh_running_nodes_alone() -> None:
    engine, nodes, queue = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)

    node = await nodes.get(video_id, "metadata")
    fresh = replace(node, status=NODE_RUNNING, started_at=datetime.now(UTC))
    await nodes.create(fresh)
    queue.clear()

    await engine.reconcile(video_id, stale_seconds=600)
    assert queue.kinds() == []
    node = await nodes.get(video_id, "metadata")
    assert node.status == NODE_RUNNING


@pytest.mark.asyncio
async def test_status_summary() -> None:
    engine, _, _ = _engine()
    video_id = uuid.uuid4()
    await engine.start(video_id)

    status = await engine.status(video_id)
    assert len(status["nodes"]) == len(WORKFLOW_GRAPH)
    by_kind = {n["kind"]: n for n in status["nodes"]}
    assert by_kind["metadata"]["status"] in (NODE_WAITING, NODE_RUNNING)
