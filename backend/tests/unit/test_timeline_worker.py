import pytest

from clipforge.config import Settings
from clipforge.intelligence.workers import build_workers
from clipforge.intelligence.workers.timeline import TimelineWorker
from clipforge.workflow.domain.graph import specs_by_kind


@pytest.mark.asyncio
async def test_timeline_worker_builds_payload_from_artifacts() -> None:
    worker = TimelineWorker()
    payload = await worker.detect(
        None,
        {
            "artifacts": {
                "scene": {"scenes": [{"start_time": 0.0, "end_time": 10.0}]},
                "motion": {"intervals": [], "max_intensity": 0.0, "has_motion": False},
                "beat": {"peaks": [1.0, 5.0], "bpm": 120.0, "has_audio": True},
            }
        },
    )

    assert payload["duration_seconds"] == 10.0
    assert payload["shot_count"] == 1
    assert payload["has_audio"] is True
    # two beats in one shot: beat_score 0.667 -> emphasis 0.367 each
    assert payload["punch_ins"] == [
        {"time": 1.0, "strength": 0.367, "reason": "beat"},
        {"time": 5.0, "strength": 0.367, "reason": "beat"},
    ]


@pytest.mark.asyncio
async def test_timeline_worker_tolerates_missing_artifacts() -> None:
    worker = TimelineWorker()
    payload = await worker.detect(None, {"artifacts": {}})
    assert payload["shot_count"] == 1
    assert payload["shots"][0]["emphasis_score"] == 0.0
    assert payload["punch_ins"] == []


def test_timeline_worker_does_not_need_source() -> None:
    assert TimelineWorker.needs_source is False
    assert TimelineWorker.input_artifacts == ("scene", "motion", "beat")


def test_timeline_worker_validate() -> None:
    worker = TimelineWorker()
    worker.validate({"shots": [], "punch_ins": []})
    with pytest.raises(ValueError, match="shots"):
        worker.validate({"shots": "nope", "punch_ins": []})
    with pytest.raises(ValueError, match="punch_ins"):
        worker.validate({"shots": [], "punch_ins": None})


def test_timeline_worker_is_registered_in_graph() -> None:
    workers = build_workers(Settings())
    assert "timeline" in workers
    assert isinstance(workers["timeline"], TimelineWorker)

    spec = specs_by_kind()["timeline"]
    assert spec.dependencies == ("scene", "motion", "beat")
