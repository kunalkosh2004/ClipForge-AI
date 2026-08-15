import uuid
from typing import Any

import pytest

from clipforge.workflow.application.recovery import sweep_stale_workflows


class StubNodeRepo:
    def __init__(self, stale_video_ids: list[uuid.UUID]) -> None:
        self._stale = stale_video_ids

    async def list_stale_video_ids(self, max_started_age_seconds: int) -> list[uuid.UUID]:
        return self._stale


class StubQueue:
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


@pytest.mark.asyncio
async def test_sweep_enqueues_reconcile_for_each_stale_video() -> None:
    v1, v2 = uuid.uuid4(), uuid.uuid4()
    queue = StubQueue()

    scheduled = await sweep_stale_workflows(
        StubNodeRepo([v1, v2]),
        queue,
        actor_name="workflow_reconcile",
        queue_name="media",
        stale_seconds=600,
    )

    assert scheduled == [str(v1), str(v2)]
    assert [m["payload"]["video_id"] for m in queue.messages] == [str(v1), str(v2)]
    assert all(m["task"] == "workflow_reconcile" for m in queue.messages)
    assert all(m["queue"] == "media" for m in queue.messages)


@pytest.mark.asyncio
async def test_sweep_is_noop_when_nothing_is_stale() -> None:
    queue = StubQueue()

    scheduled = await sweep_stale_workflows(StubNodeRepo([]), queue)

    assert scheduled == []
    assert queue.messages == []
