"""Unit + integration tests for the MotionCaption frame-sequence engine (M3)."""

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from clipforge.lyrics.application.frames import build_motion_caption_frames
from clipforge.rendering.domain.composite import CompositeRenderer
from clipforge.rendering.domain.styles import OverlayConfig, RenderStyle

WORDS = [
    {"text": "before", "start": 0.0, "end": 1.0},
    {"text": "hello", "start": 1.5, "end": 2.0},
    {"text": "motion", "start": 2.2, "end": 2.9},
    {"text": "typography", "start": 3.0, "end": 4.0},
    {"text": "after", "start": 5.0, "end": 6.0},
]


def _build_frames(tmp_path: Path, **overrides) -> Path | None:
    kwargs = dict(
        words=WORDS,
        clip_start=1.2,
        clip_end=4.5,
        preset="storytelling",
        canvas=(320, 240),
        accent_color="FFD700",
        muted_color="9E9E9E",
        animation="sweep",
        out_dir=tmp_path / "frames",
        fps=10,
    )
    kwargs.update(overrides)
    return build_motion_caption_frames(**kwargs)


def _opaque_pixels(path: Path) -> int:
    alpha = Image.open(path).convert("RGBA").getchannel("A")
    return sum(1 for p in alpha.getdata() if p > 0)


# ------------------------------------------------------------------ unit


def test_build_returns_none_without_words_in_window(tmp_path: Path) -> None:
    assert _build_frames(tmp_path, clip_start=8.0, clip_end=9.0) is None
    assert not (tmp_path / "frames").exists()


def test_build_writes_numbered_pngs(tmp_path: Path) -> None:
    result = _build_frames(tmp_path)
    assert result is not None
    pngs = sorted(result.glob("*.png"))
    # floor(3.3s * 10fps) + 1 = 34 frames, numbered 000000.png upward
    assert len(pngs) == 34
    assert pngs[0].name == "000000.png"
    assert pngs[-1].name == "000033.png"


def test_build_frames_are_rgba_with_text_pixels(tmp_path: Path) -> None:
    result = _build_frames(tmp_path)
    assert result is not None
    mid = sorted(result.glob("*.png"))[14]
    assert Image.open(mid).mode == "RGBA"
    assert _opaque_pixels(mid) > 0


def test_build_uses_full_clip_duration(tmp_path: Path) -> None:
    # clip_end - clip_start = 3.3s but the last word ends at clip-local 2.8s;
    # frames must still cover the whole clip, not just the last word.
    result = _build_frames(tmp_path, clip_end=4.5)
    assert result is not None
    assert len(list(result.glob("*.png"))) == 34


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = _build_frames(tmp_path, out_dir=tmp_path / "a")
    second = _build_frames(tmp_path, out_dir=tmp_path / "b")
    assert first is not None and second is not None
    for a, b in zip(
        sorted(first.glob("*.png")), sorted(second.glob("*.png")), strict=True
    ):
        assert a.read_bytes() == b.read_bytes()


# ------------------------------------------------- overlay-only ASS + wiring


def test_render_clip_with_frames_skips_word_ass_and_burns_overlays(
    monkeypatch, tmp_path: Path
) -> None:
    frames = _build_frames(tmp_path, clip_end=4.5)
    assert frames is not None

    captured: dict = {}
    async def fake_render_with_filter(self, *args, **kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        "clipforge.rendering.domain.composite.CompositeRenderer._render_with_filter",
        fake_render_with_filter,
    )

    import asyncio

    style = replace(RenderStyle(), overlays=OverlayConfig(emojis_enabled=True))
    renderer = CompositeRenderer(
        caption_renderer=object(), framing_analyzer=None, style=style
    )
    asyncio.run(
        renderer.render_clip(
            source_path=tmp_path / "src.mp4",
            output_path=tmp_path / "out.mp4",
            clip_start=1.2,
            clip_end=4.5,
            transcript_words=WORDS,
            canvas=(320, 240),
            emoji_triggers=[{"emoji": "🔥", "time": 0.5, "duration": 1.0}],
            caption_frames_dir=frames,
            caption_fps=10,
        )
    )

    assert captured["caption_frames_dir"] == frames
    assert captured["caption_fps"] == 10
    ass = captured["ass"]
    # overlay event burns, but no word captions in the ASS
    assert "Dialogue" in ass
    assert "hello" not in ass
    assert "motion" not in ass


# --------------------------------------------------------- real ffmpeg render


@pytest.mark.asyncio
async def test_frames_render_composites_into_output(
    tmp_path: Path, static_video: Path
) -> None:
    if static_video is None:
        pytest.skip("ffmpeg not available")
    frames = _build_frames(
        tmp_path,
        words=[
            {"text": "hello", "start": 0.0, "end": 1.0},
            {"text": "typography", "start": 1.0, "end": 2.0},
        ],
        clip_start=0.0,
        clip_end=2.0,
        canvas=(320, 240),
        fps=10,
    )
    assert frames is not None

    renderer = CompositeRenderer(
        caption_renderer=object(), framing_analyzer=None, style=RenderStyle()
    )
    out = tmp_path / "rendered.mp4"
    await renderer.render_clip(
        source_path=static_video,
        output_path=out,
        clip_start=0.0,
        clip_end=2.0,
        transcript_words=[],
        canvas=(320, 240),
        caption_frames_dir=frames,
        caption_fps=10,
    )

    import subprocess

    assert out.exists() and out.stat().st_size > 0
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,duration",
            "-of",
            "csv",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "video" in probe
    assert "320" in probe and "240" in probe

    # Frame at t=1.0: the caption text pixels differ from the flat gray source.
    def grab(path: Path, t: float) -> bytes:
        return subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                str(t),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "image2",
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout

    output_frame = grab(out, 1.0)
    source_frame = grab(static_video, 1.0)
    assert output_frame != source_frame
