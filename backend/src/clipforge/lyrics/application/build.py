"""Shared caption request building for the MotionCaption backends.

Both the ASS exporter and the frame-sequence renderer consume the same
compiled lyrics request, so the two caption backends agree on which words
belong to a clip and how they are themed.
"""

from typing import Any

from clipforge.lyrics.domain.entities import LyricsRequest, LyricWord

__all__ = ["clip_caption_request", "emphasis_indices_for_words", "window_words"]


def window_words(
    words: list[dict[str, Any]], clip_start: float, clip_end: float
) -> list[dict[str, Any]]:
    """Transcript words that fall inside the clip window, rebased to
    clip-local seconds. Mirrors the legacy windowing so all caption
    backends agree on which words belong to a clip."""
    result: list[dict[str, Any]] = []
    for word in words:
        text = str(word.get("text", "")).strip()
        start = float(word.get("start", 0.0))
        end = float(word.get("end", start + 0.1))
        if not text:
            continue
        if end <= clip_start or start >= clip_end:
            continue
        result.append(
            {
                "text": text,
                "start": max(start, clip_start) - clip_start,
                "end": min(end, clip_end) - clip_start,
            }
        )
    return result


def clip_caption_request(
    words: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    *,
    preset: str,
    canvas: tuple[int, int],
    accent_color: str,
    muted_color: str,
    animation: str,
    faces: tuple[tuple[float, float, float, float], ...] = (),
    face_margin: float = 16.0,
    theme: str | None = None,
    highlight_words: tuple[str, ...] = (),
) -> LyricsRequest | None:
    """A clip-local ``LyricsRequest`` for the words inside the window.

    ``faces`` are output-canvas boxes (left, top, right, bottom) the caption
    placement engine avoids. ``highlight_words`` become ``emphasis_indices``
    (clip-local karaoke emphasis for the matching windowed words). Returns
    None when no words fall inside the clip window so callers can fall back
    to their empty-caption behavior.
    """
    clip_words = window_words(words, clip_start, clip_end)
    if not clip_words:
        return None
    return LyricsRequest(
        words=tuple(
            LyricWord(text=w["text"], start=w["start"], end=w["end"])
            for w in clip_words
        ),
        canvas_width=canvas[0],
        canvas_height=canvas[1],
        preset=preset or None,
        theme=theme,
        accent_color=accent_color,
        muted_color=muted_color,
        animation=animation,
        karaoke=True,
        emphasis_indices=emphasis_indices_for_words(clip_words, highlight_words),
        faces=faces,
        face_margin=face_margin,
    )


def emphasis_indices_for_words(
    clip_words: list[dict[str, Any]], highlight_words: tuple[str, ...]
) -> tuple[int, ...]:
    """Clip-local word indices whose text matches a highlight word.

    Matching is case-insensitive on exact (trimmed) text so emphasis lands on
    the words the AI Director called out.
    """
    wanted = {word.strip().lower() for word in highlight_words if word.strip()}
    if not wanted:
        return ()
    return tuple(
        index
        for index, word in enumerate(clip_words)
        if str(word.get("text", "")).strip().lower() in wanted
    )
