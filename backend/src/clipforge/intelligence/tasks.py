import asyncio
import time
import uuid
from typing import Any

from clipforge.artifacts.infrastructure.repositories import SQLAlchemyArtifactRepository
from clipforge.artifacts.infrastructure.storage_store import StorageArtifactStore
from clipforge.common import logging as logging_mod
from clipforge.common.events import EVENT_WORKER_FAILED, DomainEvent, worker_completed_event
from clipforge.common.observability import (
    record_worker_completion,
    trace_id_from_context,
)
from clipforge.db.session import SessionLocal
from clipforge.intelligence.application.service import CACHED, IntelligenceService
from clipforge.intelligence.workers import build_workers
from clipforge.videos.infrastructure.repositories import SQLAlchemyVideoRepository
from clipforge.worker.tasks import _container, task, tracer
from clipforge.workflow.application.engine import WorkflowEngine
from clipforge.workflow.domain.entities import NODE_RUNNING, NODE_SKIPPED, NODE_SUCCEEDED
from clipforge.workflow.infrastructure.repositories import SQLAlchemyWorkflowNodeRepository

logger = logging_mod.get_logger(__name__)

# One dramatiq broker/container is shared with the legacy pipeline (both
# modules load into the same worker process); the intelligence actors remain
# a self-contained module so they can be moved to their own process later.
_workers = build_workers(_container.settings)


@task(queue=_container.settings.queue_media, max_retries=5, max_backoff=60_000)
def start_intelligence(payload: dict[str, Any]) -> None:
    asyncio.run(_run_start_intelligence(payload))


@task(
    queue=_container.settings.queue_media,
    max_retries=0,
    on_retry_exhausted=None,
)
def intelligence_worker(payload: dict[str, Any]) -> None:
    # Retries are owned by the Workflow Engine (attempts budget + backoff),
    # not by dramatiq, so a redelivered message can never double-run a worker.
    asyncio.run(_run_intelligence_worker(payload))


@task(queue=_container.settings.queue_media, max_retries=3, max_backoff=60_000)
def workflow_reconcile(payload: dict[str, Any]) -> None:
    asyncio.run(_run_workflow_reconcile(payload))


# ---------------------------------------------------------------------------
# start_intelligence
# ---------------------------------------------------------------------------


async def _run_start_intelligence(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    try:
        with tracer.start_as_current_span("pipeline.intelligence_start") as span:
            span.set_attribute("video_id", str(video_id))
            with logging_mod.request_context(
                video_id=str(video_id),
                stage="intelligence_start",
                trace_id=trace_id_from_context() or "none",
            ):
                await _execute_start(video_id)
    except Exception:
        logger.exception("intelligence_start_failed", video_id=str(video_id))
        raise


async def _execute_start(video_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        engine = WorkflowEngine(SQLAlchemyWorkflowNodeRepository(session), _container.queue)
        await engine.start(video_id)
        await session.commit()
    logger.info("intelligence_started", video_id=str(video_id))


# ---------------------------------------------------------------------------
# intelligence_worker
# ---------------------------------------------------------------------------


async def _run_intelligence_worker(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    kind = str(payload["kind"])
    worker = _workers.get(kind)
    if worker is None:
        logger.error("unknown_worker_kind", kind=kind, video_id=str(video_id))
        return

    total_started = time.perf_counter()
    try:
        with tracer.start_as_current_span(f"pipeline.intelligence.{kind}") as span:
            span.set_attribute("video_id", str(video_id))
            span.set_attribute("worker_kind", kind)
            with logging_mod.request_context(
                video_id=str(video_id),
                stage=kind,
                trace_id=trace_id_from_context() or "none",
            ):
                outcome, processing, queue_time = await _execute_worker(video_id, worker)
        record_worker_completion(
            kind,
            "succeeded",
            time.perf_counter() - total_started,
            processing_seconds=processing,
            queue_seconds=queue_time,
        )
        await _publish_completed(video_id, kind, worker.version, outcome)
        await _advance(video_id)
    except Exception as exc:
        logger.exception("intelligence_worker_failed", video_id=str(video_id), kind=kind)
        record_worker_completion(
            kind, "failed", time.perf_counter() - total_started
        )
        await _handle_failure(video_id, kind, exc)


async def _execute_worker(
    video_id: uuid.UUID, worker: Any
) -> tuple[str, float, float]:
    """Run the worker: claim already happened at enqueue (node is running);
    skip duplicate/stale messages; recompute only when uncached."""
    async with SessionLocal() as session:
        nodes = SQLAlchemyWorkflowNodeRepository(session)
        engine = WorkflowEngine(nodes, _container.queue)

        node = await nodes.get(video_id, worker.kind)
        if node is None or node.status not in (NODE_RUNNING, NODE_SKIPPED, NODE_SUCCEEDED):
            logger.warning(
                "intelligence_node_not_runnable",
                video_id=str(video_id),
                kind=worker.kind,
                status=getattr(node, "status", None),
            )
            return CACHED, 0.0, 0.0
        if node.status in (NODE_SKIPPED, NODE_SUCCEEDED):
            return CACHED, 0.0, 0.0

        queue_time = 0.0
        if node.started_at is not None:
            queue_time = max(0.0, time.time() - node.started_at.timestamp())

        service = IntelligenceService(
            videos=SQLAlchemyVideoRepository(session),
            artifacts=SQLAlchemyArtifactRepository(session),
            store=StorageArtifactStore(_container.storage),
            storage=_container.storage,
        )
        started = time.perf_counter()
        outcome, _artifact = await service.process(video_id, worker)
        processing = time.perf_counter() - started

        if outcome == CACHED:
            await engine.skip(video_id, worker.kind)
        else:
            await engine.succeed(video_id, worker.kind)
        await session.commit()
        return outcome, processing, queue_time


async def _publish_completed(
    video_id: uuid.UUID, kind: str, version: str, outcome: str
) -> None:
    try:
        await _container.events.publish(
            DomainEvent(
                type=worker_completed_event(kind),
                aggregate_id=str(video_id),
                payload={"kind": kind, "version": version, "cached": outcome == CACHED},
            )
        )
    except Exception:
        logger.warning(
            "worker_event_publish_failed", event_type=kind, video_id=str(video_id)
        )


async def _advance(video_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        engine = WorkflowEngine(SQLAlchemyWorkflowNodeRepository(session), _container.queue)
        await engine.advance(video_id)
        await session.commit()


async def _handle_failure(video_id: uuid.UUID, kind: str, exc: Exception) -> None:
    try:
        async with SessionLocal() as session:
            engine = WorkflowEngine(SQLAlchemyWorkflowNodeRepository(session), _container.queue)
            await engine.retry(video_id, kind, str(exc)[:500])
            await session.commit()
        await _container.events.publish(
            DomainEvent(
                type=EVENT_WORKER_FAILED,
                aggregate_id=str(video_id),
                payload={"kind": kind, "error": str(exc)[:500]},
            )
        )
    except Exception:
        logger.exception(
            "worker_failure_handling_failed", video_id=str(video_id), kind=kind
        )


# ---------------------------------------------------------------------------
# workflow_reconcile (crash recovery)
# ---------------------------------------------------------------------------


async def _run_workflow_reconcile(payload: dict[str, Any]) -> None:
    video_id = uuid.UUID(str(payload["video_id"]))
    async with SessionLocal() as session:
        engine = WorkflowEngine(SQLAlchemyWorkflowNodeRepository(session), _container.queue)
        await engine.reconcile(video_id)
        await session.commit()
    logger.info("workflow_reconciled", video_id=str(video_id))
