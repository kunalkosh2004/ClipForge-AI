"""Unit tests for canvas-space face box detection (M4a)."""

import numpy as np

from clipforge.rendering.domain.framing import CropWindow, FramingPlan
from clipforge.rendering.infrastructure import face_analyzer


def _fake_detector(boxes):
    def detect(_frame):
        return boxes

    return detect


def _frame_bytes(proxy_w: int, proxy_h: int, count: int = 1) -> bytes:
    return bytes(proxy_w * proxy_h * count)


def test_returns_empty_when_detector_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._load_face_box_detector",
        lambda _w, _h: None,
    )
    assert face_analyzer.detect_face_boxes("src.mp4", (320, 240)) == []


def test_scales_boxes_to_canvas_and_dedupes(monkeypatch) -> None:
    frames = [
        np.zeros((480, 640), dtype=np.uint8),
        np.zeros((480, 640), dtype=np.uint8),
        np.zeros((480, 640), dtype=np.uint8),
    ]
    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._load_face_box_detector",
        lambda _w, _h: _fake_detector([(10, 10, 100, 50)]),
    )
    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._read_canvas_frames",
        lambda *_a, **_k: frames,
    )
    boxes = face_analyzer.detect_face_boxes("src.mp4", (320, 240))
    # proxy is 640x480; 320x240 canvas -> scale by 0.5 both axes
    assert boxes == [(5.0, 5.0, 55.0, 30.0)]


def test_collects_multiple_distinct_boxes(monkeypatch) -> None:
    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._load_face_box_detector",
        lambda _w, _h: _fake_detector([(0, 0, 100, 100), (200, 200, 300, 300)]),
    )
    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._read_canvas_frames",
        lambda *_a, **_k: [np.zeros((480, 640), dtype=np.uint8)],
    )
    # YuNet boxes are (x, y, width, height) in proxy space, scaled by 0.5
    assert face_analyzer.detect_face_boxes("src.mp4", (320, 240)) == [
        (0.0, 0.0, 50.0, 50.0),
        (100.0, 100.0, 250.0, 250.0),
    ]


def test_returns_empty_when_decode_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._load_face_box_detector",
        lambda _w, _h: _fake_detector([(1, 1, 2, 2)]),
    )

    def boom(*_a, **_k):
        raise OSError("decode failed")

    monkeypatch.setattr(
        "clipforge.rendering.infrastructure.face_analyzer._read_canvas_frames", boom
    )
    assert face_analyzer.detect_face_boxes("src.mp4", (320, 240)) == []


def test_read_canvas_frames_uses_crop_chain_with_framing(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return type("Proc", (), {"stdout": _frame_bytes(64, 48, 2)})()

    monkeypatch.setattr(face_analyzer.subprocess, "run", fake_run)
    framing = FramingPlan(
        window=CropWindow(width=160, height=120),
        x_expression="10.0",
        y_expression="20.0",
    )
    frames = face_analyzer._read_canvas_frames(
        "src.mp4", (320, 240), (64, 48), framing
    )
    assert len(frames) == 2
    vf = captured["cmd"][captured["cmd"].index("-vf") + 1]
    assert "crop=160:120:'10.0':'20.0',scale=64:48" in vf
    assert f"fps={face_analyzer.SAMPLE_FPS}," in vf


def test_read_canvas_frames_uses_pad_for_landscape(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return type("Proc", (), {"stdout": _frame_bytes(64, 48)})()

    monkeypatch.setattr(face_analyzer.subprocess, "run", fake_run)
    frames = face_analyzer._read_canvas_frames("src.mp4", (320, 240), (64, 48), None)
    assert len(frames) == 1
    vf = captured["cmd"][captured["cmd"].index("-vf") + 1]
    assert "force_original_aspect_ratio=decrease" in vf
    assert "pad=64:48" in vf
    assert "crop" not in vf


def test_load_face_box_detector_returns_none_without_model(monkeypatch) -> None:
    monkeypatch.setattr(face_analyzer.os.path, "exists", lambda _p: False)
    assert face_analyzer._load_face_box_detector(640, 480) is None


def test_load_face_box_detector_returns_none_without_cv2(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert face_analyzer._load_face_box_detector(640, 480) is None
