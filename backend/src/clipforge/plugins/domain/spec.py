"""Plugin renderer domain: context + plugin contract.

A `RendererPlugin` is a deterministic translator for one timeline track. It
never makes creative decisions: it reads the in-window, clip-local
`TimelineEvent`s handed to it and writes typed operations into the shared
`RenderContext`. The pipeline then compiles the context into a `FilterBatch`
for the composite encoder.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from clipforge.clips.domain.entities import Clip
from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.rendering.domain.framing import FramingPlan
from clipforge.rendering.domain.styles import RenderStyle
from clipforge.rendering.domain.zoom import ZoomKeyframe


@dataclass
class RenderContext:
    """Mutable per-clip render state the plugins write into.

    Time values are clip-local seconds (already windowed by the compiler).
    ``style`` is the resolved preset/style baseline; plugins that want to
    override a caption attribute set ``caption_updates`` and the pipeline
    applies them via ``replace`` before captions are built.
    """

    clip: Clip
    canvas: tuple[int, int]
    clip_start: float
    clip_end: float
    clip_duration: float
    preset: str
    style: RenderStyle
    words: list[dict[str, Any]]
    framing: FramingPlan | None = None
    faces: tuple[tuple[float, float, float, float], ...] = ()
    emphasis_times: list[float] = field(default_factory=list)

    zoom_keyframes: list[ZoomKeyframe] = field(default_factory=list)
    grade_filters: list[str] = field(default_factory=list)

    overlay_events: list[dict[str, Any]] = field(default_factory=list)
    lower_third_text: str | None = None
    cta_text: str | None = None

    music_path: str | None = None
    music_volume_db: float | None = None
    sfx_triggers: list[dict[str, Any]] = field(default_factory=list)

    caption_updates: dict[str, Any] = field(default_factory=dict)
    caption_theme: str | None = None
    caption_highlight_words: list[str] = field(default_factory=list)

    transition: dict[str, Any] | None = None


class RendererPlugin(ABC):
    """One plugin per timeline track, each exposing ``apply``.

    ``track`` is the blueprint track name; a plugin may be registered under
    alias track names (e.g. the color plugin also serves ``effects``).
    """

    track: str

    @abstractmethod
    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        """Translate ``events`` into operations on ``ctx``."""
