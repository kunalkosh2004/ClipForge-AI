"""MotionCaption frame-sequence backend: transcript words -> RGBA caption PNGs.

The primary caption backend. Every clip-local time step gets an RGBA frame
(transparent everywhere except the typography), written as ``000000.png``,
``000001.png``, … at the clip fps. The composite renderer feeds the sequence
to ffmpeg's image2 demuxer and ``overlay`` filter, so captions composite with
arbitrary pixel animation instead of being limited to libass features.
"""

from pathlib import Path
from typing import Any

from motion_caption import Canvas, TimelineRenderer

from clipforge.lyrics.application.build import clip_caption_request
from clipforge.lyrics.application.service import LyricsService

__all__ = ["build_motion_caption_frames"]


def build_motion_caption_frames(
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    *,
    preset: str,
    canvas: tuple[int, int],
    accent_color: str,
    muted_color: str,
    animation: str,
    out_dir: Path,
    fps: int = 30,
    faces: tuple[tuple[float, float, float, float], ...] = (),
    face_margin: float = 16.0,
    theme: str | None = None,
    highlight_words: tuple[str, ...] = (),
) -> Path | None:
    """Render caption frames for the clip window into ``out_dir``.

    Returns ``out_dir`` on success, or None when no words fall inside the
    clip window (nothing to render).
    """
    request = clip_caption_request(
        words,
        clip_start,
        clip_end,
        preset=preset,
        canvas=canvas,
        accent_color=accent_color,
        muted_color=muted_color,
        animation=animation,
        faces=faces,
        face_margin=face_margin,
        theme=theme,
        highlight_words=highlight_words,
    )
    if request is None:
        return None
    compiled = LyricsService().compile_lyrics(request)
    TimelineRenderer().render_sequence_to_directory(
        compiled.timeline,
        Canvas(width=canvas[0], height=canvas[1]),
        out_dir,
        fps=fps,
        start=0.0,
        end=max(clip_end - clip_start, 0.1),
    )
    return out_dir
