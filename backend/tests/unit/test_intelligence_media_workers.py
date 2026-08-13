from pathlib import Path

import pytest

from clipforge.intelligence.workers.metadata import MetadataWorker
from clipforge.intelligence.workers.motion import MotionWorker
from clipforge.intelligence.workers.scene import SceneWorker, _duration_from_artifacts


@pytest.mark.asyncio
async def test_metadata_worker_detects_codec_resolution_and_checksum(
    tone_video: Path,
) -> None:
    worker = MetadataWorker()
    payload = await worker.detect(tone_video, {})
    assert payload["checksum"]
    assert payload["size_bytes"] > 0
    assert payload["duration_seconds"] == pytest.approx(2.0, abs=0.5)
    assert payload["width"] == 320
    assert payload["height"] == 240
    assert payload["codec"] == "h264"
    assert payload["audio_codec"] == "aac"
    assert payload["thumbnail_base64"]


@pytest.mark.asyncio
async def test_scene_worker_detects_boundary(scene_test_video: Path) -> None:
    pytest.importorskip("scenedetect", reason="pyscenedetect not installed")
    worker = SceneWorker()
    payload = await worker.detect(scene_test_video, {})
    assert payload["scene_count"] >= 1
    assert payload["method"] == "pyscenedetect.content"
    for scene in payload["scenes"]:
        assert scene["end_time"] > scene["start_time"]
        assert scene["duration"] == pytest.approx(scene["end_time"] - scene["start_time"])


@pytest.mark.asyncio
async def test_scene_worker_falls_back_to_single_scene(tone_video: Path) -> None:
    pytest.importorskip("scenedetect", reason="pyscenedetect not installed")
    worker = SceneWorker()
    payload = await worker.detect(tone_video, {})
    assert payload["scene_count"] >= 1
    assert payload["scenes"][0]["start_time"] == 0.0


def test_scene_fallback_duration_from_artifacts() -> None:
    params = {"artifacts": {"metadata": {"duration_seconds": 12.5}}}
    assert _duration_from_artifacts(params) == 12.5
    assert _duration_from_artifacts({"artifacts": {"metadata": None}}) is None


@pytest.mark.asyncio
async def test_motion_worker_static_video_has_no_motion(static_video: Path) -> None:
    worker = MotionWorker()
    payload = await worker.detect(static_video, {})
    assert payload["has_motion"] is False
    assert payload["mean_intensity"] < 0.01
    assert all(i["intensity"] == 0.0 for i in payload["intervals"])


@pytest.mark.asyncio
async def test_motion_worker_moving_video_has_motion(moving_video: Path) -> None:
    worker = MotionWorker()
    payload = await worker.detect(moving_video, {})
    assert payload["has_motion"] is True
    assert payload["mean_intensity"] > 0
    assert payload["intervals"], "expected sampled intervals for a moving source"
    for interval in payload["intervals"]:
        assert "t" in interval and "intensity" in interval
