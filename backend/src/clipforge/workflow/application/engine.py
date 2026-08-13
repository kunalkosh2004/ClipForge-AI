import uuid
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.common.ports import QueueBroker
from clipforge.workflow.domain.entities import (
    ACTIVE_STATUSES,
    NODE_FAILED,
    NODE_RUNNING,
    NODE_WAITING,
    SATISFIED_STATUSES,
    WorkflowNode,
)
from clipforge.workflow.domain.graph import WORKFLOW_GRAPH, specs_by_kind
from clipforge.workflow.domain.ports import WorkflowNodeRepository

logger = logging_mod.get_logger(__name__)

DEFAULT_STALE_SECONDS = 600


class WorkflowEngine:
    """Advances the per-video DAG by enqueuing nodes whose dependencies are
    satisfied. Idempotent: `ensure` never duplicates nodes, `advance` claims
    (waiting -> running) a node atomically before enqueueing it, and stale
    `running` nodes are reset by `reconcile` so the workflow resumes after a
    crash.
    """

    def __init__(
        self,
        nodes: WorkflowNodeRepository,
        queue: QueueBroker,
        *,
        graph: tuple[Any, ...] = WORKFLOW_GRAPH,
        actor_name: str = "intelligence_worker",
    ) -> None:
        self._nodes = nodes
        self._queue = queue
        self._graph = graph
        self._actor_name = actor_name
        self._specs = specs_by_kind()

    # -- setup ---------------------------------------------------------------

    async def ensure(self, video_id: uuid.UUID) -> list[WorkflowNode]:
        """Create any missing nodes for the video's DAG (idempotent)."""
        existing = {node.kind: node for node in await self._nodes.list_for_video(video_id)}
        created: list[WorkflowNode] = []
        for spec in self._graph:
            if spec.kind in existing:
                continue
            node = await self._nodes.create(
                WorkflowNode(
                    video_id=video_id,
                    kind=spec.kind,
                    depends_on=spec.dependencies,
                    queue=spec.queue,
                )
            )
            created.append(node)
        if created:
            logger.info(
                "workflow_nodes_created",
                video_id=str(video_id),
                kinds=[n.kind for n in created],
            )
        return created

    async def start(self, video_id: uuid.UUID) -> list[WorkflowNode]:
        """Ensure the DAG exists and enqueue every currently-ready node."""
        await self.ensure(video_id)
        return await self.advance(video_id)

    # -- node state ----------------------------------------------------------

    async def succeed(self, video_id: uuid.UUID, kind: str) -> None:
        node = await self._nodes.get(video_id, kind)
        if node is None:
            return
        await self._nodes.mark_succeeded(node.id)

    async def skip(self, video_id: uuid.UUID, kind: str) -> None:
        node = await self._nodes.get(video_id, kind)
        if node is None:
            return
        await self._nodes.mark_skipped(node.id)

    async def fail(self, video_id: uuid.UUID, kind: str, error: str) -> None:
        node = await self._nodes.get(video_id, kind)
        if node is None:
            return
        await self._nodes.mark_failed(node.id, error)
        logger.warning("workflow_node_failed", video_id=str(video_id), kind=kind, error=error[:500])

    async def retry(
        self,
        video_id: uuid.UUID,
        kind: str,
        error: str,
        max_backoff_ms: int = 60_000,
        base_backoff_ms: int = 1_000,
    ) -> bool:
        """Re-claim a failed node (waiting -> running) and re-enqueue it with
        exponential backoff — or permanently fail the node when the attempt
        budget is exhausted. The engine (not the worker, not dramatiq) owns
        retry policy. Returns True when the node was re-enqueued.
        """
        node = await self._nodes.get(video_id, kind)
        if node is None:
            return False
        if node.attempts >= node.max_attempts:
            await self._nodes.mark_failed(node.id, error)
            logger.warning(
                "workflow_node_retries_exhausted",
                video_id=str(video_id),
                kind=kind,
                attempts=node.attempts,
                error=error[:500],
            )
            return False
        backoff = min(max_backoff_ms, base_backoff_ms * 2 ** max(0, node.attempts - 1))
        claimed = await self._nodes.mark_running(node.id)
        if claimed is None:
            return False
        self._queue.enqueue(
            self._actor_name,
            {"video_id": str(video_id), "kind": node.kind},
            queue=node.queue,
            delay=backoff,
        )
        logger.info(
            "workflow_node_retry_scheduled",
            video_id=str(video_id),
            kind=kind,
            attempts=claimed.attempts,
            backoff_ms=backoff,
            error=error[:500],
        )
        return True

    # -- advancement ---------------------------------------------------------

    async def advance(self, video_id: uuid.UUID) -> list[WorkflowNode]:
        """Enqueue every waiting node whose dependencies have produced
        artifacts. Claims nodes (waiting -> running) before enqueueing so a
        node can never be enqueued twice.
        """
        by_kind = {node.kind: node for node in await self._nodes.list_for_video(video_id)}
        ready: list[WorkflowNode] = []
        for node in by_kind.values():
            if node.status != NODE_WAITING:
                continue
            if not self._dependencies_satisfied(node, by_kind):
                continue
            claimed = await self._nodes.mark_running(node.id)
            if claimed is None:
                continue
            self._queue.enqueue(
                self._actor_name,
                {"video_id": str(video_id), "kind": node.kind},
                queue=node.queue,
            )
            ready.append(claimed)
            logger.info(
                "workflow_node_enqueued",
                video_id=str(video_id),
                kind=node.kind,
                queue=node.queue,
            )
        return ready

    def _dependencies_satisfied(
        self, node: WorkflowNode, by_kind: dict[str, WorkflowNode]
    ) -> bool:
        for dep in node.depends_on:
            dep_node = by_kind.get(dep)
            if dep_node is None or dep_node.status not in SATISFIED_STATUSES:
                return False
        return True

    # -- recovery ------------------------------------------------------------

    async def reconcile(
        self, video_id: uuid.UUID, stale_seconds: int = DEFAULT_STALE_SECONDS
    ) -> None:
        """Crash recovery: reset stale `running` nodes to `waiting` (or fail
        them once the attempt budget is exhausted), then re-enqueue anything
        that became ready.
        """
        stale = await self._nodes.reset_stale(video_id, stale_seconds)
        for node in stale:
            if node.attempts >= node.max_attempts:
                await self._nodes.mark_failed(node.id, "max attempts exceeded after crash recovery")
                logger.warning(
                    "workflow_node_exhausted",
                    video_id=str(video_id),
                    kind=node.kind,
                    attempts=node.attempts,
                )
            else:
                logger.info(
                    "workflow_node_reset_for_retry",
                    video_id=str(video_id),
                    kind=node.kind,
                    attempts=node.attempts,
                )
        await self.advance(video_id)

    # -- status helpers ------------------------------------------------------

    async def status(self, video_id: uuid.UUID) -> dict[str, Any]:
        """Compact per-video workflow state (for admin/debug and tests)."""
        nodes = await self._nodes.list_for_video(video_id)
        return {
            "video_id": str(video_id),
            "nodes": [
                {
                    "kind": n.kind,
                    "status": n.status,
                    "attempts": n.attempts,
                    "depends_on": list(n.depends_on),
                    "error": n.error,
                }
                for n in nodes
            ],
            "done": all(n.status in SATISFIED_STATUSES + (NODE_FAILED,) for n in nodes),
        }


__all__ = ["ACTIVE_STATUSES", "NODE_WAITING", "NODE_RUNNING", "WorkflowEngine"]
