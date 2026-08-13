"""Unit tests for face-aware caption wiring (M4a)."""

from types import SimpleNamespace
from typing import Any

from motion_caption import SubtitleTimeline

from clipforge.lyrics.application.ass import build_motion_caption_ass
from clipforge.lyrics.application.build import clip_caption_request
from clipforge.lyrics.application.frames import build_motion_caption_frames
from clipforge.lyrics.domain.entities import LyricsRequest, LyricWord
from clipforge.lyrics.infrastructure.motion_caption import MotionCaptionLyricsCompiler

FACES = ((5.0, 5.0, 55.0, 30.0), (200.0, 100.0, 300.0, 180.0))


def _compiled() -> SimpleNamespace:
    return SimpleNamespace(timeline=SubtitleTimeline())


def _request(monkeypatch, **kwargs) -> Any:
    captured: dict = {}

    def fake_compile(req):
        captured["req"] = req
        return SubtitleTimeline()

    monkeypatch.setattr(
        "clipforge.lyrics.infrastructure.motion_caption.compile", fake_compile
    )
    base = dict(
        words=(LyricWord(text="hello", start=0.0, end=1.0),),
        faces=FACES,
        face_margin=24.0,
        karaoke=True,
    )
    base.update(kwargs)
    MotionCaptionLyricsCompiler().compile(LyricsRequest(**base))
    return captured["req"]


def test_compiler_maps_faces_to_face_aware_placement(monkeypatch) -> None:
    req = _request(monkeypatch)
    assert len(req.faces) == 2
    for face, expected in zip(req.faces, FACES, strict=True):
        assert (face.box.left, face.box.top, face.box.right, face.box.bottom) == expected
    placement = req.options.placement
    assert placement is not None
    assert placement.strategy == "face-aware"
    assert placement.face_margin == 24.0
    assert req.options.karaoke is True


def test_compiler_keeps_default_placement_without_faces(monkeypatch) -> None:
    req = _request(monkeypatch, faces=())
    assert req.faces == []
    assert req.options.placement is None


def test_clip_caption_request_carries_faces() -> None:
    request = clip_caption_request(
        [{"text": "hello", "start": 0.0, "end": 1.0}],
        0.0,
        2.0,
        preset="storytelling",
        canvas=(320, 240),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
        faces=FACES,
        face_margin=12.0,
    )
    assert request is not None
    assert request.faces == FACES
    assert request.face_margin == 12.0


def test_ass_builder_propagates_faces(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    def fake_compile(self, request):
        captured["request"] = request
        return _compiled()

    monkeypatch.setattr(
        "clipforge.lyrics.application.ass.LyricsService", lambda: type(
            "S", (), {"compile_lyrics": fake_compile}
        )()
    )
    result = build_motion_caption_ass(
        [{"text": "hello", "start": 0.0, "end": 1.0}],
        0.0,
        2.0,
        preset="storytelling",
        canvas=(320, 240),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
        faces=FACES,
    )
    assert result is not None
    assert captured["request"].faces == FACES


def test_frames_builder_propagates_faces(monkeypatch, tmp_path) -> None:
    captured: dict = {}

    def fake_compile(self, request):
        captured["request"] = request
        return _compiled()

    def fake_render(self, timeline, canvas, out_dir, **kwargs):
        captured["canvas"] = (canvas.width, canvas.height)

    monkeypatch.setattr(
        "clipforge.lyrics.application.frames.LyricsService", lambda: type(
            "S", (), {"compile_lyrics": fake_compile}
        )()
    )
    monkeypatch.setattr(
        "clipforge.lyrics.application.frames.TimelineRenderer", lambda: type(
            "R", (), {"render_sequence_to_directory": fake_render}
        )()
    )
    result = build_motion_caption_frames(
        [{"text": "hello", "start": 0.0, "end": 1.0}],
        0.0,
        2.0,
        preset="storytelling",
        canvas=(320, 240),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
        out_dir=tmp_path / "frames",
        faces=FACES,
    )
    assert result is not None
    assert captured["request"].faces == FACES
    assert captured["canvas"] == (320, 240)
