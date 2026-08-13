"""Compile a blueprint timeline into per-clip, per-track event lists.

Events use source-video seconds in the blueprint. A per-clip render only
executes events whose timestamp falls inside the clip window `[start, end)`,
shifted to clip-local time. Transition events sit on clip boundaries and are
the M6 final assembler's job, so they are excluded from per-clip renders.
"""

from __future__ import annotations

from typing import Any

from clipforge.directing.domain.blueprint import TimelineEvent

EXCLUDED_TRACKS = frozenset({"transition"})


def compile_clip_events(
    blueprint: dict[str, Any] | None,
    clip_start: float,
    clip_end: float,
) -> dict[str, list[TimelineEvent]]:
    """Group in-window blueprint events by track, in clip-local seconds.

    Malformed events are skipped defensively so one bad entry can never take
    down a render. Events whose track has no registered plugin are still
    returned here; the pipeline silently ignores tracks it cannot resolve.
    """
    events = _timeline_events(blueprint)
    grouped: dict[str, list[TimelineEvent]] = {}
    for raw in events:
        track = _event_track(raw)
        if track is None or track in EXCLUDED_TRACKS:
            continue
        timestamp = _event_float(raw, "timestamp")
        if timestamp is None or not (clip_start <= timestamp < clip_end):
            continue
        local = round(timestamp - clip_start, 3)
        grouped.setdefault(track, []).append(
            TimelineEvent(
                track=track,
                type=_event_type(raw),
                timestamp=local,
                duration=_event_float(raw, "duration") or 0.0,
                parameters=dict(_event_parameters(raw)),
                reason=_event_reason(raw),
            )
        )
    return grouped


def _timeline_events(blueprint: dict[str, Any] | None) -> list[Any]:
    if not isinstance(blueprint, dict):
        return []
    timeline = blueprint.get("timeline")
    if not isinstance(timeline, dict):
        return []
    events = timeline.get("events")
    return events if isinstance(events, list) else []


def _event_track(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    track = raw.get("track")
    return track if isinstance(track, str) and track else None


def _event_type(raw: dict[str, Any]) -> str:
    value = raw.get("type")
    return value if isinstance(value, str) and value else "event"


def _event_float(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None  # NaN guard


def _event_parameters(raw: dict[str, Any]) -> dict[str, Any]:
    value = raw.get("parameters")
    return value if isinstance(value, dict) else {}


def _event_reason(raw: dict[str, Any]) -> str:
    value = raw.get("reason")
    return value if isinstance(value, str) else ""
