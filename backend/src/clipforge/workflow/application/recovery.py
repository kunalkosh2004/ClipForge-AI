import asyncio
from typing import Any

from dramatiq.broker import Broker
from dramatiq.middleware import Middleware

from clipforge.common import logging as logging_mod
from clipforge.common.ports import QueueBroker
from clipforge.db.session import SessionLocal
from clipforge.workflow.application.engine import DEFAULT_STALE_SECONDS
from clipforge.workflow.domain.ports import WorkflowNodeRepository
from clipforge.workflow.infrastructure.repositories import SQLAlchemyWorkflowNodeRepository

logger = logging_mod.get_logger(__name__)


async def sweep_stale_workflows(
    nodes: WorkflowNodeRepository,
    queue: QueueBroker,
    *,
    actor_name: str = "workflow_reconcile",
    queue_name: str = "media",
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> list[str]:
    """Find every video with a running node left stale by a crashed worker
    and schedule `workflow_reconcile` for it. Idempotent and cheap — the
    reconcile task itself is a no-op when nothing is stale.
    """
    video_ids = await nodes.list_stale_video_ids(stale_seconds)
    for video_id in video_ids:
        queue.enqueue(actor_name, {"video_id": str(video_id)}, queue=queue_name)
        logger.info(
            "workflow_reconcile_scheduled",
            video_id=str(video_id),
            stale_seconds=stale_seconds,
        )
    return [str(v) for v in video_ids]


class WorkflowRecoveryMiddleware(Middleware):
    """Crash recovery: when a worker process boots, sweep for workflow nodes
    left `running` by a previous worker that died mid-job (e.g. OOM) and
    enqueue recovery for their videos.

    `after_worker_boot` fires once per worker process after all actors are
    registered, so the sweep never races actor declaration. A DB failure at
    boot is logged and swallowed — the worker still starts.
    """

    def __init__(
        self,
        *,
        queue: QueueBroker,
        actor_name: str = "workflow_reconcile",
        queue_name: str = "media",
        stale_seconds: int = DEFAULT_STALE_SECONDS,
    ) -> None:
        self._queue = queue
        self._actor_name = actor_name
        self._queue_name = queue_name
        self._stale_seconds = stale_seconds

    def after_worker_boot(self, broker: Broker, worker: Any) -> None:  # type: ignore[no-untyped-def]
        try:
            asyncio.run(self._sweep())
        except Exception:
            logger.exception("workflow_recovery_sweep_failed")

    async def _sweep(self) -> None:
        async with SessionLocal() as session:
            nodes = SQLAlchemyWorkflowNodeRepository(session)
            await sweep_stale_workflows(
                nodes,
                self._queue,
                actor_name=self._actor_name,
                queue_name=self._queue_name,
                stale_seconds=self._stale_seconds,
            )
