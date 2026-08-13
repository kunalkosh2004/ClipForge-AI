"""MotionCaption ASS backend: transcript words -> animated ASS subtitles.

This is the drop-in replacement for the legacy ``build_caption_ass``. It
windows transcript words to the clip, compiles them with the MotionCaption
engine (theme/colors/animation from the render style) and exports the result
as an ASS document whose PlayRes matches the output canvas, ready to be
burned with ffmpeg's ``ass`` filter.
"""

from typing import Any, cast

from motion_caption.exporters import EXPORTER_REGISTRY, AssExporter

from clipforge.lyrics.application.build import clip_caption_request, window_words
from clipforge.lyrics.application.service import LyricsService

__all__ = ["build_motion_caption_ass", "window_words"]


def build_motion_caption_ass(
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    *,
    preset: str,
    canvas: tuple[int, int],
    accent_color: str,
    muted_color: str,
    animation: str,
    fps: int = 30,
    faces: tuple[tuple[float, float, float, float], ...] = (),
    face_margin: float = 16.0,
    theme: str | None = None,
    highlight_words: tuple[str, ...] = (),
) -> str | None:
    """Build an ASS subtitle document from the MotionCaption engine.

    Returns None when no words fall inside the clip window so callers can
    fall back to the legacy path's empty caption track.
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
    exporter = cast(AssExporter, EXPORTER_REGISTRY.get("ass"))
    return str(exporter.export(compiled.timeline, fps=fps).data)
