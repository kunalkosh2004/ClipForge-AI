"""Lyrics input contracts for the motion-typography compiler."""

from __future__ import annotations

from dataclasses import dataclass

from motion_caption import SubtitleTimeline


@dataclass(frozen=True, slots=True)
class LyricWord:
    """One transcript word on a clip's local timeline (seconds, 0-based)."""

    text: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class LyricsRequest:
    """Compile request for the motion-typography engine for one clip.

    ``words`` are already window-filtered to the clip and rebased so the
    first in-window word starts at or after 0.0. ``preset`` is the ClipForge
    preset id used for the default theme mapping; ``theme`` is an explicit
    MotionCaption theme name that wins over the preset mapping. Caption
    colors mirror the ClipForge semantics: ``muted_color`` paints the
    non-active words, ``accent_color`` paints the active/emphasized words.
    """

    words: tuple[LyricWord, ...] = ()
    canvas_width: int = 1920
    canvas_height: int = 1080
    fps: int = 30
    preset: str | None = None
    theme: str | None = None
    accent_color: str | None = None
    muted_color: str | None = None
    animation: str | None = None
    emphasis_indices: tuple[int, ...] = ()
    karaoke: bool = False
    platform: str | None = None
    safe_area: dict[str, float] | None = None
    faces: tuple[tuple[float, float, float, float], ...] = ()
    face_margin: float = 16.0


@dataclass(frozen=True, slots=True)
class CompiledLyrics:
    """The deterministic compilation result for a clip.

    ``timeline`` is the canonical MotionCaption IR every backend consumes;
    the scalars are convenience accessors so callers need not walk the IR.
    """

    request: LyricsRequest
    theme_name: str
    timeline: SubtitleTimeline
    event_count: int
    word_count: int
    duration: float
