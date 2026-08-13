import asyncio
from pathlib import Path
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.intelligence.workers.base import IntelligenceWorker
from clipforge.processing.infrastructure.ffprobe import build_metadata, run_ffprobe

logger = logging_mod.get_logger(__name__)

_CONTENT_THRESHOLD = 27.0


class SceneWorker(IntelligenceWorker):
    """Shot boundaries via PySceneDetect's content detector.

    Consumes the `metadata` artifact only as a duration fallback when no scene
    boundary is detected (a single-scene video still yields one scene entry).
    """

    kind = "scene"
    version = "scene-v1"
    input_artifacts = ("metadata",)

    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        assert source_path is not None  # scene detection needs the source
        return await asyncio.to_thread(_detect_scenes, source_path, params)


def _detect_scenes(source_path: Path, params: dict[str, Any]) -> dict[str, Any]:
    try:
        scenes = _pyscenedetect(source_path)
    except RuntimeError:
        logger.warning("scene_detector_unavailable", error="pyscenedetect not installed")
        scenes = []
    if scenes:
        return {
            "scenes": scenes,
            "method": "pyscenedetect.content",
            "threshold": _CONTENT_THRESHOLD,
            "scene_count": len(scenes),
        }
    # No boundary detected -> the whole clip is one scene.
    duration = _duration_from_artifacts(params) or _probe_duration(source_path)
    return {
        "scenes": [
            {"start_time": 0.0, "end_time": duration, "duration": duration}
        ],
        "method": "fallback_single_scene",
        "threshold": _CONTENT_THRESHOLD,
        "scene_count": 1,
    }


def _pyscenedetect(source_path: Path) -> list[dict[str, float]]:
    try:
        from scenedetect import SceneManager, open_video  # type: ignore[import-not-found]
        from scenedetect.detectors import ContentDetector  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pyscenedetect is not installed") from exc

    video = open_video(str(source_path))
    manager = SceneManager()
    manager.auto_downscale = True
    manager.add_detector(ContentDetector(threshold=_CONTENT_THRESHOLD))
    manager.detect(video)

    scenes: list[dict[str, float]] = []
    for scene in manager.get_scene_list():
        start = _to_seconds(scene[0])
        end = _to_seconds(scene[1])
        if end - start > 0.1:
            scenes.append(
                {
                    "start_time": round(start, 3),
                    "end_time": round(end, 3),
                    "duration": round(end - start, 3),
                }
            )
    return scenes


def _to_seconds(value: Any) -> float:
    if hasattr(value, "get_seconds"):
        return float(value.get_seconds())
    return float(value)


def _duration_from_artifacts(params: dict[str, Any]) -> float | None:
    meta = (params.get("artifacts") or {}).get("metadata") or {}
    duration = meta.get("duration_seconds")
    return float(duration) if duration else None


def _probe_duration(source_path: Path) -> float:
    try:
        meta = build_metadata(run_ffprobe(source_path))
        duration = meta["format"].get("duration")
        return float(duration) if duration else 0.0
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("scene_probe_failed", error=str(exc)[:200])
        return 0.0
