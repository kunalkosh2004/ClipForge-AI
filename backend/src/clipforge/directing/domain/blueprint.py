"""Editing blueprint: the typed contract between the AI Director and the renderer.

The Director (an AI that behaves like a professional editor) watches the whole
video and produces a single `EditingBlueprint`. Every creative decision lives
here: the global style baseline (color grading, subtitle theme, music) and a
per-track timeline of events. Every timeline event carries
`timestamp` / `duration` / `parameters` / `reason`.

The renderer is deterministic — it executes these events exactly and never
makes creative decisions of its own.

Timeline semantics
------------------
Events use *source-video* seconds. When a clip window `[start, end]` is
rendered, only events whose timestamp falls inside the window are applied
(shifted to clip-local time). Transition events sit on clip boundaries and are
used by the final-cut assembler, not by per-clip renders.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Track(StrEnum):
    """The named lanes a professional editor plans on."""

    CAMERA = "camera"
    SUBTITLE = "subtitle"
    TRANSITION = "transition"
    OVERLAY = "overlay"
    EMOJI = "emoji"
    MUSIC = "music"
    EFFECTS = "effects"
    CTA = "cta"


VALID_TRACKS = frozenset(t.value for t in Track)

TRACK_ORDER = tuple(t.value for t in Track)


class ColorGrading(BaseModel):
    """Global color baseline applied to the whole edit. All optional so a
    sparse output degrades to a neutral (ungraded) pass."""

    style: str | None = None
    brightness: float | None = None
    contrast: float | None = None
    temperature: float | None = None
    saturation: float | None = None
    vibrance: float | None = None
    bloom: float | None = None
    glow: float | None = None
    film_grain: float | None = None
    vignette: float | None = None


class SubtitleTheme(BaseModel):
    """The caption look for the whole edit (premium CapCut-style captions)."""

    font: str | None = None
    weight: str | None = None
    stroke: float | None = None
    shadow: float | None = None
    alignment: str | int | None = None
    animation: str | None = None
    background: str | None = None
    highlight_words: list[str] = Field(default_factory=list)
    word_animation: str | None = None
    reading_speed: float | None = None
    safe_area: str | None = None
    colors: list[str] = Field(default_factory=list)


class MusicStyle(BaseModel):
    """Background music direction for the whole edit."""

    mood: str | None = None
    volume_db: float | None = None
    ducking_db: float | None = None
    bpm: float | None = None


class GlobalStyle(BaseModel):
    style_name: str | None = None
    color_grading: ColorGrading = Field(default_factory=ColorGrading)
    subtitle_theme: SubtitleTheme = Field(default_factory=SubtitleTheme)
    music: MusicStyle = Field(default_factory=MusicStyle)
    camera_philosophy: str | None = None
    editing_philosophy: str | None = None


class BlueprintClip(BaseModel):
    """One shot from the source video, with its role in the story."""

    start_time: str | float
    end_time: str | float
    hook: str | None = None
    thumbnail_text: str | None = None
    viral_score: float = 0.0
    retention_score: float = 0.0
    story_role: str | None = None


class TimelineEvent(BaseModel):
    """A single executable instruction on one timeline track.

    `track` and `type` are validated by the normalizer (the raw AI output may
    use aliases); `parameters` is a free-form dict the plugins read with typed
    accessors. Every event must be justified by `reason` so the renderer never
    invents motivation.
    """

    track: str
    type: str
    timestamp: float = 0.0
    duration: float = 0.0
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""

    @field_validator("track", "type", "reason", mode="before")
    @classmethod
    def _coerce_null_strings(cls, value: Any) -> Any:
        """The raw AI output sometimes emits `null` for optional string
        fields; treat it as empty so the normalizer can drop the event
        instead of the whole blueprint failing validation."""
        return "" if value is None else value


class EditTimeline(BaseModel):
    events: list[TimelineEvent] = Field(default_factory=list)


class EditingBlueprint(BaseModel):
    """The complete, executable edit for one source video."""

    schema_version: int = 1
    preset: str = "default"
    global_style: GlobalStyle = Field(default_factory=GlobalStyle)
    clips: list[BlueprintClip] = Field(default_factory=list)
    timeline: EditTimeline = Field(default_factory=EditTimeline)
