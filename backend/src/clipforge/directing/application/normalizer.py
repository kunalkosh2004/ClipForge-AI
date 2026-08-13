"""Deterministic director pass over the AI's raw editing blueprint.

The renderer never guesses, but the AI can still hallucinate — out-of-range
timestamps, unknown track names, malformed parameters. This module repairs the
blueprint deterministically: it clamps, validates, de-dupes and sorts. It
never invents creative decisions (an empty track stays empty), so the
renderer's input is always safe and always executable exactly as-is.
"""

from __future__ import annotations

import re
from typing import Any

from clipforge.common import logging as logging_mod
from clipforge.common.times import parse_timestamp
from clipforge.directing.domain.blueprint import (
    TRACK_ORDER,
    VALID_TRACKS,
    BlueprintClip,
    ColorGrading,
    EditingBlueprint,
    EditTimeline,
    GlobalStyle,
    MusicStyle,
    SubtitleTheme,
    TimelineEvent,
)

logger = logging_mod.get_logger(__name__)

MIN_CLIP_SECONDS = 20.0
MAX_CLIP_SECONDS = 45.0
OVERLAP_GUARD_SECONDS = 1.0

MAX_EVENT_DURATION_SECONDS = 30.0
MAX_REASON_LENGTH = 200

_TRACK_ALIASES: dict[str, str] = {
    "camera": "camera",
    "cam": "camera",
    "camera_plan": "camera",
    "subtitle": "subtitle",
    "subtitles": "subtitle",
    "caption": "subtitle",
    "captions": "subtitle",
    "subtitle_plan": "subtitle",
    "transition": "transition",
    "transitions": "transition",
    "transition_plan": "transition",
    "overlay": "overlay",
    "overlays": "overlay",
    "overlay_plan": "overlay",
    "emoji": "emoji",
    "emojis": "emoji",
    "emoji_plan": "emoji",
    "music": "music",
    "music_plan": "music",
    "audio": "music",
    "audio_plan": "music",
    "effects": "effects",
    "effect": "effects",
    "sfx": "effects",
    "sfx_plan": "effects",
    "audio_fx": "effects",
    "cta": "cta",
    "cta_plan": "cta",
    "call_to_action": "cta",
}

_EVENT_TYPES: dict[str, frozenset[str]] = {
    "camera": frozenset(
        {
            "punch_zoom",
            "slow_zoom",
            "push_in",
            "push_out",
            "pan_left",
            "pan_right",
            "hold",
            "shake",
            "face_track",
        }
    ),
    "subtitle": frozenset({"phrase", "highlight_word", "flash_word"}),
    "transition": frozenset({"cut", "flash", "whip", "blur", "slide", "fade", "zoom"}),
    "overlay": frozenset({"hook", "lower_third", "progress_bar", "logo", "subscribe"}),
    "emoji": frozenset({"pop", "slide_in", "bounce"}),
    "music": frozenset({"start", "stop", "intensity_change", "duck_on", "duck_off"}),
    "effects": frozenset({"whoosh", "boom", "impact", "riser", "echo", "reverb"}),
    "cta": frozenset({"show_cta", "animate_subscribe"}),
}

_MAX_EVENTS_PER_TRACK: dict[str, int] = {
    "camera": 40,
    "subtitle": 200,
    "transition": 8,
    "overlay": 20,
    "emoji": 30,
    "music": 12,
    "effects": 40,
    "cta": 6,
}

_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")

_ALLOWED_WEIGHTS = frozenset({"bold", "semibold", "regular"})
_ALLOWED_ALIGNMENTS = frozenset({"bottom", "top", "center"})
_ALLOWED_ANIMATIONS = frozenset(
    {"sweep", "typewriter", "fade", "pop", "slide", "bounce", "glitch"}
)
_ALLOWED_SAFE_AREAS = frozenset({"default", "wide", "narrow"})
_ALLOWED_MOODS = frozenset(
    {"energetic", "chill", "suspense", "upbeat", "emotional", "epic"}
)


def normalize_blueprint(
    blueprint: EditingBlueprint,
    duration_seconds: float | None,
    target_duration: float | None = None,
) -> EditingBlueprint:
    """Sanitize a raw director output into a safely executable blueprint."""
    duration = duration_seconds or float("inf")

    clips = _normalize_clips(blueprint.clips, duration, target_duration)
    events = _normalize_events(blueprint.timeline.events, duration)
    global_style = _normalize_global_style(blueprint.global_style)

    return EditingBlueprint(
        schema_version=blueprint.schema_version,
        preset=(blueprint.preset or "default").strip().lower() or "default",
        global_style=global_style,
        clips=clips,
        timeline=EditTimeline(events=events),
    )


# ---------------------------------------------------------------------------
# clips
# ---------------------------------------------------------------------------


def _normalize_clips(
    clips: list[BlueprintClip], duration: float, target_duration: float | None
) -> list[BlueprintClip]:
    preferred = _preferred_duration(target_duration)
    cleaned: list[BlueprintClip] = []
    last_end: float | None = None
    for clip in sorted(clips, key=_clip_start):
        start = _clamp(parse_timestamp(clip.start_time), 0.0, duration)
        end = _clamp(parse_timestamp(clip.end_time), 0.0, duration)
        if start > end:
            start, end = end, start
        if end - start <= 0.0:
            continue
        if end - start > MAX_CLIP_SECONDS:
            end = start + MAX_CLIP_SECONDS
        if last_end is not None and start < last_end - OVERLAP_GUARD_SECONDS:
            continue
        cleaned.append(
            BlueprintClip(
                start_time=round(start, 3),
                end_time=round(end, 3),
                hook=_clean_text(clip.hook, 200),
                thumbnail_text=_clean_text(clip.thumbnail_text, 60),
                viral_score=_sanitize_score(clip.viral_score),
                retention_score=_sanitize_score(clip.retention_score),
                story_role=_clean_text(clip.story_role, 40),
            )
        )
        last_end = end

    return _extend_short_clips(cleaned, duration, preferred)


def _preferred_duration(target_duration: float | None) -> float:
    if target_duration is None:
        return MIN_CLIP_SECONDS
    return _clamp(float(target_duration), MIN_CLIP_SECONDS, MAX_CLIP_SECONDS)


def _extend_short_clips(
    clips: list[BlueprintClip], duration: float, preferred: float
) -> list[BlueprintClip]:
    result: list[BlueprintClip] = []
    for index, clip in enumerate(clips):
        start, end = float(clip.start_time), float(clip.end_time)
        if end - start >= MIN_CLIP_SECONDS:
            result.append(clip)
            continue
        upper_bound = (
            parse_timestamp(clips[index + 1].start_time)
            if index + 1 < len(clips)
            else duration
        )
        upper_bound = min(upper_bound - OVERLAP_GUARD_SECONDS, duration)
        target_end = min(start + preferred, start + MAX_CLIP_SECONDS)
        end = min(target_end, upper_bound)
        if end <= start:
            end = start + MIN_CLIP_SECONDS
        result.append(
            BlueprintClip(
                start_time=clip.start_time,
                end_time=round(min(end, duration), 3),
                hook=clip.hook,
                thumbnail_text=clip.thumbnail_text,
                viral_score=clip.viral_score,
                retention_score=clip.retention_score,
                story_role=clip.story_role,
            )
        )
    return result


def _clip_start(clip: BlueprintClip) -> float:
    return parse_timestamp(clip.start_time)


# ---------------------------------------------------------------------------
# timeline events
# ---------------------------------------------------------------------------


def _normalize_events(
    events: list[TimelineEvent], duration: float
) -> list[TimelineEvent]:
    accepted: list[TimelineEvent] = []
    dropped = 0
    for event in events:
        track = _resolve_track(event.track)
        if track is None:
            dropped += 1
            continue
        event_type = str(event.type or "").strip().lower()
        if event_type not in _EVENT_TYPES[track]:
            dropped += 1
            continue
        timestamp = _finite_float(event.timestamp)
        if timestamp is None or timestamp < 0.0 or timestamp > duration:
            dropped += 1
            continue
        event_duration = _finite_float(event.duration)
        accepted.append(
            TimelineEvent(
                track=track,
                type=event_type,
                timestamp=round(timestamp, 3),
                duration=_clamp(
                    event_duration if event_duration is not None else 0.0,
                    0.0,
                    MAX_EVENT_DURATION_SECONDS,
                ),
                parameters=_sanitize_parameters(event.parameters),
                reason=_clean_text(event.reason, MAX_REASON_LENGTH),
            )
        )

    if dropped:
        logger.warning(
            "blueprint_events_dropped",
            dropped=dropped,
            kept=len(accepted),
        )

    capped: list[TimelineEvent] = []
    counts: dict[str, int] = {track: 0 for track in VALID_TRACKS}
    for event in sorted(accepted, key=lambda e: (e.timestamp, e.type, e.reason)):
        if counts[event.track] >= _MAX_EVENTS_PER_TRACK[event.track]:
            continue
        counts[event.track] += 1
        capped.append(event)

    return sorted(
        capped,
        key=lambda e: (_track_index(e.track), e.timestamp, e.type),
    )


def _resolve_track(value: Any) -> str | None:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if raw in VALID_TRACKS:
        return raw
    return _TRACK_ALIASES.get(raw)


def _track_index(track: str) -> int:
    return TRACK_ORDER.index(track)


# ---------------------------------------------------------------------------
# global style
# ---------------------------------------------------------------------------


def _normalize_global_style(style: GlobalStyle) -> GlobalStyle:
    return GlobalStyle(
        style_name=_clean_text(style.style_name, 80),
        color_grading=_normalize_color_grading(style.color_grading),
        subtitle_theme=_normalize_subtitle_theme(style.subtitle_theme),
        music=_normalize_music_style(style.music),
        camera_philosophy=_clean_text(style.camera_philosophy, 500),
        editing_philosophy=_clean_text(style.editing_philosophy, 500),
    )


def _normalize_color_grading(grading: ColorGrading) -> ColorGrading:
    return ColorGrading(
        style=_clean_text(grading.style, 80),
        brightness=_optional_clamp(grading.brightness, -100.0, 100.0),
        contrast=_optional_clamp(grading.contrast, -100.0, 100.0),
        temperature=_optional_clamp(grading.temperature, -100.0, 100.0),
        saturation=_optional_clamp(grading.saturation, -100.0, 100.0),
        vibrance=_optional_clamp(grading.vibrance, -100.0, 100.0),
        bloom=_optional_clamp(grading.bloom, 0.0, 100.0),
        glow=_optional_clamp(grading.glow, 0.0, 100.0),
        film_grain=_optional_clamp(grading.film_grain, 0.0, 100.0),
        vignette=_optional_clamp(grading.vignette, 0.0, 100.0),
    )


def _normalize_subtitle_theme(theme: SubtitleTheme) -> SubtitleTheme:
    return SubtitleTheme(
        font=_clean_text(theme.font, 60),
        weight=_one_of(theme.weight, _ALLOWED_WEIGHTS),
        stroke=_optional_clamp(theme.stroke, 0.0, 100.0),
        shadow=_optional_clamp(theme.shadow, 0.0, 100.0),
        alignment=_one_of(theme.alignment, _ALLOWED_ALIGNMENTS),
        animation=_one_of(theme.animation, _ALLOWED_ANIMATIONS),
        background=_sanitize_background(theme.background),
        highlight_words=_sanitize_strings(theme.highlight_words, limit=20, max_len=40),
        word_animation=_clean_text(theme.word_animation, 40),
        reading_speed=_optional_clamp(theme.reading_speed, 100.0, 300.0),
        safe_area=_one_of(theme.safe_area, _ALLOWED_SAFE_AREAS),
        colors=_sanitize_hex_colors(theme.colors, limit=3),
    )


def _normalize_music_style(music: MusicStyle) -> MusicStyle:
    return MusicStyle(
        mood=_one_of(music.mood, _ALLOWED_MOODS),
        volume_db=_optional_clamp(music.volume_db, -40.0, 0.0),
        ducking_db=_optional_clamp(music.ducking_db, -40.0, 0.0),
        bpm=_optional_clamp(music.bpm, 40.0, 200.0),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sanitize_parameters(parameters: Any) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return {}
    return {str(key): value for key, value in parameters.items()}


def _sanitize_hex_colors(colors: list[Any] | None, limit: int = 3) -> list[str]:
    if not colors:
        return []
    result: list[str] = []
    for color in colors:
        value = str(color or "").strip().lstrip("#").upper()
        if not _HEX_RE.match(value):
            continue
        if value in result:
            continue
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _sanitize_background(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if cleaned == "none":
        return None
    stripped = cleaned.lstrip("#").upper()
    return stripped if _HEX_RE.match(stripped) else None


def _sanitize_strings(
    values: list[Any] | None, limit: int, max_len: int
) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        cleaned = _clean_text(value, max_len)
        if not cleaned:
            continue
        if cleaned in result:
            continue
        result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _clean_text(value: Any, max_len: int) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned[:max_len] or None


def _one_of(value: Any, allowed: frozenset[str]) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    return cleaned if cleaned in allowed else None


def _optional_clamp(value: Any, low: float, high: float) -> float | None:
    number = _finite_float(value)
    if number is None:
        return None
    return round(_clamp(number, low, high), 3)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _sanitize_score(value: Any) -> float:
    number = _finite_float(value)
    if number is None:
        return 0.0
    return round(_clamp(number, 0.0, 100.0), 1)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
