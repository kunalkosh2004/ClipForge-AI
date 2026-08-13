"""Subject tracking for smart re-framing.

Frames are decoded through an ffmpeg rawvideo pipe so the analyzer has no
direct media dependency. Per sampled frame the subject center is the detected
face center (OpenCV YuNet ONNX detector, optional) or, when no face is
visible, the center-of-mass of inter-frame motion.

For YouTube Shorts style (9:16), we apply a vertical offset (headroom) so the
subject's face sits in the upper third of the frame, leaving space for
captions/UI at the bottom.
"""

from __future__ import annotations

import os
import subprocess

import numpy as np

from clipforge.common import logging as logging_mod
from clipforge.rendering.domain.framing import TrackPoint
from clipforge.rendering.domain.ports import FramingAnalyzer

logger = logging_mod.get_logger(__name__)

SAMPLE_FPS = 2.0
PROXY_WIDTH = 640
_MOTION_WEIGHT_FLOOR = 0.005
_MOTION_THRESHOLD = 12

# YouTube Shorts style: face should be in upper ~35% of frame
# This translates to a vertical offset in normalized coordinates (0..1)
SHORTS_HEADROOM_OFFSET = 0.15  # Move crop window up by 15% of frame height


class OpenCVFramingAnalyzer(FramingAnalyzer):
    def analyze(
        self,
        source_path: str,
        source_width: int,
        source_height: int,
    ) -> list[TrackPoint]:
        try:
            frames = _read_gray_frames(source_path, source_width, source_height)
        except (subprocess.CalledProcessError, OSError) as exc:
            logger.warning("framing_read_failed", error=str(exc)[:200])
            return []
        if not frames:
            return []
        detector = _load_face_detector(PROXY_WIDTH, frames[0].shape[0])
        points = _roi_track(frames, detector)
        # Apply Shorts-style headroom offset for vertical videos
        return [_apply_headroom(p, source_width, source_height) for p in points]


def _read_gray_frames(
    source_path: str,
    source_width: int,
    source_height: int,
) -> list[np.ndarray]:
    """Sample the clip as low-res grayscale frames via ffmpeg rawvideo."""
    proxy_height = max(1, round(PROXY_WIDTH * source_height / max(1, source_width)))
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", source_path,
        "-vf", f"fps={SAMPLE_FPS},scale={PROXY_WIDTH}:{proxy_height}",
        "-an",
        "-pix_fmt", "gray",
        "-f", "rawvideo",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    frame_size = PROXY_WIDTH * proxy_height
    data = proc.stdout
    frames = [
        np.frombuffer(data[start : start + frame_size], dtype=np.uint8).reshape(
            proxy_height, PROXY_WIDTH
        )
        for start in range(0, len(data) - frame_size + 1, frame_size)
    ]
    return frames


def _roi_track(
    frames: list[np.ndarray],
    face_detector: object | None,
) -> list[TrackPoint]:
    points: list[TrackPoint] = []
    prev: np.ndarray | None = None
    for index, frame in enumerate(frames):
        center = _roi_for_frame(frame, prev, face_detector)
        if center is not None:
            x, y, mode = center
            points.append(TrackPoint(t=index / SAMPLE_FPS, x=x, y=y, mode=mode))
        prev = frame
    return points


def _roi_for_frame(
    gray: np.ndarray,
    prev_gray: np.ndarray | None,
    face_detector: object | None,
) -> tuple[float, float, str] | None:
    """Return (x, y, mode) normalized subject center, or None if untrackable."""
    if face_detector is not None:
        center = face_detector(gray)
        if center is not None:
            return center[0], center[1], "face"
    if prev_gray is None:
        return None
    diff = np.abs(gray.astype(np.int16) - prev_gray.astype(np.int16)).astype(np.uint8)
    moving = diff > _MOTION_THRESHOLD
    if moving.mean() < _MOTION_WEIGHT_FLOOR:
        return None
    ys, xs = np.nonzero(moving)
    cx = xs.mean() / gray.shape[1]
    cy = ys.mean() / gray.shape[0]
    return cx, cy, "motion"


def _apply_headroom(point: TrackPoint, source_width: int, source_height: int) -> TrackPoint:
    """Apply YouTube Shorts style vertical offset (headroom) to track point.

    For 9:16 output, we want the subject's face in the upper portion of the frame
    to leave room for captions and UI elements at the bottom.
    """
    # Only apply headroom for face detections (more reliable), not motion
    if point.mode == "face":
        # Move the tracked center up by the headroom offset
        # Clamp to valid range
        new_y = max(0.0, min(1.0, point.y - SHORTS_HEADROOM_OFFSET))
        return TrackPoint(t=point.t, x=point.x, y=new_y, mode=point.mode)
    return point


def _load_face_detector(proxy_width: int, proxy_height: int) -> object | None:
    """YuNet ONNX face detector wrapped as ``img -> (cx, cy) | None``.

    Falls back to None (motion tracking only) when OpenCV or the bundled
    model file is unavailable.
    """
    try:
        import cv2
    except Exception:
        logger.info("opencv_unavailable; framing falls back to motion tracking")
        return None
    model_path = os.environ.get("OPENCV_FACE_MODEL", "/opt/opencv/face_detection_yunet.onnx")
    if not os.path.exists(model_path):
        logger.info("face model not found; framing falls back to motion tracking")
        return None
    try:
        detector = cv2.FaceDetectorYN.create(
            model_path,
            "",
            (proxy_width, proxy_height),
            score_threshold=0.6,
        )
    except Exception:
        logger.info("face detector init failed; framing falls back to motion tracking")
        return None

    def detect(gray: np.ndarray) -> tuple[float, float] | None:
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        _, faces = detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return None
        best = faces[0]
        x, y, w, h = best[:4]
        return (x + w / 2) / gray.shape[1], (y + h / 2) / gray.shape[0]

    return detect
