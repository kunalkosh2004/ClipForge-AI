"""Canvas-space face box detection for caption placement.

Frames are decoded through the same crop/scale chain the composite renderer
uses (or a plain scale/pad fallback when there is no smart framing), so the
detected boxes are directly comparable with the caption placement engine's
canvas. OpenCV YuNet is optional: any failure (missing OpenCV, missing model
file, decode error) degrades to an empty box list and captions keep their
default placement.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence

import numpy as np

from clipforge.common import logging as logging_mod
from clipforge.rendering.domain.framing import FramingPlan

logger = logging_mod.get_logger(__name__)

SAMPLE_FPS = 2.0
PROXY_WIDTH = 640
_SCORE_THRESHOLD = 0.6


def detect_face_boxes(
    source_path: str,
    canvas: tuple[int, int],
    framing: FramingPlan | None = None,
) -> list[tuple[float, float, float, float]]:
    """Face boxes in output-canvas pixels: ``(left, top, right, bottom)``.

    Sampling the clip at a low proxy rate keeps this cheap; repeated boxes
    across sampled frames are deduplicated. Returns ``[]`` whenever the model
    or decoder is unavailable.
    """
    canvas_w, canvas_h = canvas
    if canvas_w <= 0 or canvas_h <= 0:
        return []
    proxy_height = max(1, round(PROXY_WIDTH * canvas_h / canvas_w))
    detector = _load_face_box_detector(PROXY_WIDTH, proxy_height)
    if detector is None:
        return []
    try:
        frames = _read_canvas_frames(
            source_path, canvas, (PROXY_WIDTH, proxy_height), framing
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        logger.warning("face_sample_read_failed", error=str(exc)[:200])
        return []
    if not frames:
        return []

    seen: set[tuple[int, int, int, int]] = set()
    boxes: list[tuple[float, float, float, float]] = []
    for frame in frames:
        for x, y, w, h in detector(frame):
            left = round(x * canvas_w / PROXY_WIDTH)
            top = round(y * canvas_h / proxy_height)
            right = round((x + w) * canvas_w / PROXY_WIDTH)
            bottom = round((y + h) * canvas_h / proxy_height)
            key = (left, top, right, bottom)
            if key in seen:
                continue
            seen.add(key)
            boxes.append((float(left), float(top), float(right), float(bottom)))
    return boxes


def _read_canvas_frames(
    source_path: str,
    canvas: tuple[int, int],
    proxy: tuple[int, int],
    framing: FramingPlan | None,
) -> list[np.ndarray]:
    """Sample the clip as proxy grayscale frames in output-canvas space."""
    proxy_w, proxy_h = proxy
    if framing is not None:
        vf = (
            f"crop={framing.window.width}:{framing.window.height}:"
            f"'{framing.x_expression}':'{framing.y_expression}',"
            f"scale={proxy_w}:{proxy_h}"
        )
    elif canvas[0] / canvas[1] > 1.0:
        vf = (
            f"scale={proxy_w}:{proxy_h}:force_original_aspect_ratio=decrease,"
            f"pad={proxy_w}:{proxy_h}:(ow-iw)/2:(oh-ih)/2"
        )
    else:
        vf = (
            f"scale={proxy_w}:{proxy_h}:force_original_aspect_ratio=increase,"
            f"crop={proxy_w}:{proxy_h}"
        )
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", source_path,
        "-vf", f"fps={SAMPLE_FPS},{vf}",
        "-an",
        "-pix_fmt", "gray",
        "-f", "rawvideo",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    frame_size = proxy_w * proxy_h
    data = proc.stdout
    return [
        np.frombuffer(data[start : start + frame_size], dtype=np.uint8).reshape(
            proxy_h, proxy_w
        )
        for start in range(0, len(data) - frame_size + 1, frame_size)
    ]


def _load_face_box_detector(
    proxy_width: int, proxy_height: int
) -> Callable[[np.ndarray], Sequence[tuple[float, float, float, float]]] | None:
    """YuNet ONNX detector wrapped as ``gray frame -> [(x, y, w, h)]``.

    Falls back to None (no face-aware placement) when OpenCV or the model
    file is unavailable, mirroring the framing analyzer's degradation.
    """
    try:
        import cv2
    except Exception:
        logger.info("opencv_unavailable; captions skip face-aware placement")
        return None
    model_path = os.environ.get("OPENCV_FACE_MODEL", "/opt/opencv/face_detection_yunet.onnx")
    if not os.path.exists(model_path):
        logger.info("face model not found; captions skip face-aware placement")
        return None
    try:
        detector = cv2.FaceDetectorYN.create(
            model_path,
            "",
            (proxy_width, proxy_height),
            score_threshold=_SCORE_THRESHOLD,
        )
    except Exception:
        logger.info("face detector init failed; captions skip face-aware placement")
        return None

    def detect(gray: np.ndarray) -> Sequence[tuple[float, float, float, float]]:
        bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        _, faces = detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return ()
        return [tuple(float(v) for v in face[:4]) for face in faces]  # type: ignore[misc]

    return detect
