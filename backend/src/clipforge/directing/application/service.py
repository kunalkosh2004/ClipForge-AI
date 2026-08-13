"""DirectorService: runs the AI Director and normalizes its output.

The service owns the boundary between the AI and the rest of the pipeline:

1. Call `ai.direct(...)` — the model returns a raw `EditingBlueprint`.
2. `normalize_blueprint(...)` — a deterministic safety pass that repairs
   hallucinated timestamps/parameters without inventing creative decisions.
3. `legacy_plan_from_blueprint(...)` — derives a backward-compatible
   `editing_plan` dict so existing consumers (clip extraction, the legacy
   composite renderer, API responses) keep working while the blueprint is the
   new single source of truth.
"""

from __future__ import annotations

import statistics
from typing import Any

from clipforge.common.ports import AIProvider, VideoInput, VideoUnderstanding
from clipforge.common.times import parse_timestamp
from clipforge.directing.application.normalizer import normalize_blueprint
from clipforge.directing.domain.blueprint import EditingBlueprint, TimelineEvent

_CAMERA_EMPHASIS_TYPES = frozenset(
    {"punch_zoom", "slow_zoom", "push_in", "push_out", "shake"}
)
_LEGACY_STYLE_KEYS = (
    "caption_style",
    "caption_colors",
    "transition_style",
    "sfx_enabled",
    "sfx_types",
    "music_mood",
    "music_volume_db",
    "emojis_enabled",
    "punch_zooms",
    "zoom_intensity",
    "cta_enabled",
    "cta_text",
)


class DirectorService:
    def __init__(self, ai: AIProvider) -> None:
        self._ai = ai

    async def direct(
        self,
        video: VideoInput,
        preset: str | None = None,
        context: VideoUnderstanding | None = None,
        editing_style: str | None = None,
    ) -> tuple[EditingBlueprint, dict[str, Any]]:
        """Direct the edit and return (normalized blueprint, legacy plan dict).

        The legacy plan is derived so downstream code that still reads
        `editing_plan` keeps functioning during the transition to blueprints.
        """
        raw = await self._ai.direct(
            video,
            preset=preset,
            context=context,
            editing_style=editing_style,
        )
        duration = (
            context.duration_seconds
            if context is not None
            else video.duration_seconds
        )
        normalized = normalize_blueprint(raw, duration)
        return normalized, legacy_plan_from_blueprint(normalized)


def legacy_plan_from_blueprint(blueprint: EditingBlueprint) -> dict[str, Any]:
    """Project a blueprint onto the legacy `editing_plan` JSON shape.

    Camera/emoji/overlay/cta events are windowed into their clip and shifted
    to clip-local seconds so the legacy composite renderer behaves sensibly
    until the blueprint-driven plugin renderer (M5) takes over.
    """
    events = list(blueprint.timeline.events)
    clips: list[dict[str, Any]] = []
    for clip in blueprint.clips:
        start = parse_timestamp(clip.start_time)
        end = parse_timestamp(clip.end_time)
        duration = max(end - start, 0.0)
        window = [
            e for e in events if e.timestamp >= start and e.timestamp <= end
        ]

        emphasis = sorted(
            {
                round(e.timestamp - start, 3)
                for e in window
                if e.track == "camera" and e.type in _CAMERA_EMPHASIS_TYPES
                if 0.0 < e.timestamp - start < duration
            }
        )[:8]
        emoji_triggers = [
            {
                "emoji": _param(e, "emoji", "✨"),
                "time": round(e.timestamp - start, 3),
            }
            for e in window
            if e.track == "emoji" and 0.0 <= e.timestamp - start < duration
        ][:8]

        clips.append(
            {
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "hook": clip.hook,
                "thumbnail_text": clip.thumbnail_text,
                "viral_score": clip.viral_score,
                "emotion": clip.story_role,
                "category": clip.story_role,
                "emphasis_times": emphasis,
                "emoji_triggers": emoji_triggers,
                "hook_text": _first_text(window, ("overlay",), ("hook",)),
                "cta_text": _first_text(window, ("cta", "overlay"), ("show_cta", "subscribe")),
            }
        )

    return {
        "preset": blueprint.preset,
        "clips": clips,
        "thumbnail_text": clips[0]["thumbnail_text"] if clips else None,
        "virality_index": _virality_index(clips),
        "preset_confidence": 1.0,
        "style": _legacy_style(blueprint, events),
    }


def _legacy_style(blueprint: EditingBlueprint, events: list[TimelineEvent]) -> dict[str, Any]:
    style = blueprint.global_style
    style_dict: dict[str, object] = {
        "caption_style": style.subtitle_theme.animation or "sweep",
        "caption_colors": style.subtitle_theme.colors or None,
        "transition_style": _transition_style(events),
        "sfx_enabled": any(e.track == "effects" for e in events),
        "sfx_types": sorted({e.type for e in events if e.track == "effects"}),
        "music_mood": style.music.mood,
        "music_volume_db": style.music.volume_db,
        "emojis_enabled": any(e.track == "emoji" for e in events),
        "punch_zooms": any(
            e.track == "camera" and e.type in ("punch_zoom", "shake") for e in events
        ),
        "zoom_intensity": _max_strength(events),
        "cta_enabled": any(e.track == "cta" for e in events),
        "cta_text": _first_text(events, ("cta",), ("show_cta", "animate_subscribe")),
    }
    return {key: style_dict[key] for key in _LEGACY_STYLE_KEYS}


def _transition_style(events: list[TimelineEvent]) -> str | None:
    for event in sorted(events, key=lambda e: e.timestamp):
        if event.track == "transition" and event.type != "cut":
            return event.type
    return None


def _max_strength(events: list[TimelineEvent]) -> float | None:
    max_strength: float | None = None
    for event in events:
        if event.track != "camera":
            continue
        strength = _as_float(event.parameters.get("strength"))
        if strength is None:
            continue
        max_strength = strength if max_strength is None else max(max_strength, strength)
    if max_strength is None:
        return None
    return round(min(max(max_strength, 0.0), 1.0), 3)


def _first_text(
    events: list[TimelineEvent], tracks: tuple[str, ...], types: tuple[str, ...]
) -> str | None:
    for event in sorted(events, key=lambda e: e.timestamp):
        if event.track in tracks and event.type in types:
            text = event.parameters.get("text")
            if text and str(text).strip():
                return str(text).strip()[:80]
    return None


def _param(event: TimelineEvent, key: str, default: str) -> str:
    value = event.parameters.get(key)
    return str(value).strip()[:8] if value is not None else default


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _virality_index(clips: list[dict[str, Any]]) -> float:
    if not clips:
        return 0.0
    return round(statistics.mean(float(c["viral_score"]) for c in clips), 1)
