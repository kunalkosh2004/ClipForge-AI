import asyncio
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from clipforge.intelligence.workers.base import IntelligenceWorker

SAMPLE_FPS = 2.0
ANALYSIS_WIDTH = 640
_DIRECTION_BINS = 8


class MotionWorker(IntelligenceWorker):
    """Global motion profile via dense OpenCV optical flow (Farneback).

    The video is sampled at `SAMPLE_FPS` fps by seeking, so CPU cost stays
    proportional to duration, not framerate. Produces a per-interval
    intensity/direction summary plus global aggregates — consumed later by the
    Timeline Engine to time camera moves and emphasis shots.
    """

    kind = "motion"
    version = "motion-v1"
    input_artifacts = ("metadata",)

    async def detect(
        self, source_path: Path | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        assert source_path is not None  # motion analysis needs the source
        return await asyncio.to_thread(_analyze_motion, source_path)


def _analyze_motion(path: Path) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {
            "intervals": [],
            "mean_intensity": 0.0,
            "max_intensity": 0.0,
            "error": "cannot_open",
        }
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        step = fps / SAMPLE_FPS

        prev_gray: np.ndarray | None = None
        intervals: list[dict[str, float]] = []
        frame_idx = 0
        while True:
            target = int(round(frame_idx * step))
            if total_frames and target >= total_frames:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            gray = _prepare_gray(frame)
            if prev_gray is None:
                prev_gray = gray
                continue
            flow_prev = np.zeros((prev_gray.shape[0], prev_gray.shape[1], 2), dtype=np.float32)
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, flow_prev, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            t = round(target / fps, 3)
            dx = round(float(np.mean(flow[..., 0])), 4)
            dy = round(float(np.mean(flow[..., 1])), 4)
            intensity = round(float(np.mean(mag)), 4)
            intervals.append(
                {
                    "t": t,
                    "intensity": intensity,
                    "dx": dx,
                    "dy": dy,
                    "direction_deg": round(math.degrees(float(np.mean(ang))) % 360.0, 1),
                }
            )
            prev_gray = gray

        if not intervals:
            return {
                "intervals": [],
                "mean_intensity": 0.0,
                "max_intensity": 0.0,
                "sample_fps": SAMPLE_FPS,
                "has_motion": False,
            }
        mean_intensity = float(np.mean([i["intensity"] for i in intervals]))
        max_intensity = float(np.max([i["intensity"] for i in intervals]))
        return {
            "intervals": intervals,
            "sample_fps": SAMPLE_FPS,
            "analysis_width": ANALYSIS_WIDTH,
            "mean_intensity": round(mean_intensity, 4),
            "max_intensity": round(max_intensity, 4),
            "has_motion": mean_intensity > 0.01,
        }
    finally:
        cap.release()


def _prepare_gray(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    if w > ANALYSIS_WIDTH:
        scale = ANALYSIS_WIDTH / w
        frame = cv2.resize(frame, (ANALYSIS_WIDTH, max(1, int(h * scale))))
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
