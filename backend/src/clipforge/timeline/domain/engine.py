"""Timeline engine: shot-level emphasis scoring and punch-in/cut timing.

A pure, deterministic function of the intelligence artifacts produced by the
M1 workers (scene boundaries, motion profile, beat profile). It never touches
the source file, storage, or the database, which keeps it trivially testable
and cacheable by the `timeline` worker.
"""

import math
from typing import Any

# A punch-in must live in a shot scoring at least this emphasis.
MIN_EMPHASIS = 0.35
# Punch-ins closer than this are collapsed into one (keep the strongest).
DEDUPE_WINDOW = 0.4
# Minimum gap between accepted punch-ins so zooms never overlap chaotically.
MIN_PUNCH_GAP = 0.6
# Hard cap so a busy track cannot flood the render with zoom pulses.
MAX_PUNCH_INS = 10
# Motion above this normalized intensity counts as a visual punch candidate.
MOTION_PEAK_THRESHOLD = 0.6

_EMPHASIS_BEAT_WEIGHT = 0.55
_EMPHASIS_MOTION_WEIGHT = 0.45

_SCHEMA_VERSION = 1


def build_timeline(
    scenes: dict[str, Any] | None,
    motion: dict[str, Any] | None,
    beats: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute the timeline artifact payload from the three M1 artifacts.

    Graceful under missing artifacts: a missing scene profile becomes a single
    whole-video shot; missing motion/beat profiles contribute zero scores.
    """
    scene_list = _as_list((scenes or {}).get("scenes"))
    intervals = _as_list((motion or {}).get("intervals"))
    peak_list = _as_list((beats or {}).get("peaks"))

    duration = _infer_duration(scene_list, intervals, peak_list)
    if not scene_list:
        scene_list = [
            {"start_time": 0.0, "end_time": duration, "duration": duration}
        ]

    normalized_intervals = [_normalize_interval(i) for i in intervals]
    max_intensity = _safe_float((motion or {}).get("max_intensity"), 0.0)
    beat_times = sorted({_safe_float(t) for t in peak_list})

    shots = [
        _score_shot(
            index,
            shot,
            normalized_intervals,
            max_intensity,
            beat_times,
        )
        for index, shot in enumerate(_normalize_scenes(scene_list))
    ]

    punch_ins = _build_punch_ins(shots, normalized_intervals, max_intensity, beat_times)
    cut_points = _cut_points(shots, duration)

    return {
        "schema_version": _SCHEMA_VERSION,
        "duration_seconds": round(duration, 3),
        "has_motion": bool((motion or {}).get("has_motion")),
        "has_audio": bool((beats or {}).get("has_audio")),
        "bpm": _optional_float((beats or {}).get("bpm")),
        "shot_count": len(shots),
        "shots": shots,
        "cut_points": cut_points,
        "punch_ins": punch_ins,
    }


def _score_shot(
    index: int,
    shot: dict[str, float],
    intervals: list[dict[str, float]],
    max_intensity: float,
    beat_times: list[float],
) -> dict[str, float]:
    start, end = shot["start_time"], shot["end_time"]
    motion_score = _shot_motion_score(start, end, intervals, max_intensity)
    beat_count = sum(1 for t in beat_times if start <= t < end)
    emphasis = _EMPHASIS_MOTION_WEIGHT * motion_score
    if beat_count:
        emphasis += _EMPHASIS_BEAT_WEIGHT * min(beat_count, 3) / 3.0
    return {
        "id": index,
        "start_time": round(start, 3),
        "end_time": round(end, 3),
        "duration": round(max(end - start, 0.0), 3),
        "motion_score": round(motion_score, 3),
        "beat_score": round(min(beat_count, 3) / 3.0, 3),
        "emphasis_score": round(min(max(emphasis, 0.0), 1.0), 3),
    }


def _shot_motion_score(
    start: float,
    end: float,
    intervals: list[dict[str, float]],
    max_intensity: float,
) -> float:
    if not intervals or max_intensity <= 0.0:
        return 0.0
    values = [
        i["intensity"]
        for i in intervals
        if start <= i["t"] < end and math.isfinite(i["intensity"])
    ]
    if not values:
        return 0.0
    return min(sum(values) / len(values) / max_intensity, 1.0)


def _build_punch_ins(
    shots: list[dict[str, float]],
    intervals: list[dict[str, float]],
    max_intensity: float,
    beat_times: list[float],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for t in beat_times:
        shot = _shot_at(shots, t)
        if shot is None:
            continue
        strength = shot["emphasis_score"]
        if strength >= MIN_EMPHASIS:
            candidates.append({"time": t, "strength": strength, "reason": "beat"})

    for interval in _motion_peaks(intervals, max_intensity):
        t = interval["t"]
        shot = _shot_at(shots, t)
        if shot is None:
            continue
        strength = interval["intensity"] / max_intensity if max_intensity > 0 else 0.0
        candidates.append(
            {
                "time": t,
                "strength": min(max(strength, 0.0), 1.0),
                "reason": "motion",
            }
        )

    merged = _dedupe(candidates, window=DEDUPE_WINDOW)
    picked = _spread(merged, gap=MIN_PUNCH_GAP, limit=MAX_PUNCH_INS)
    return sorted(
        [
            {
                "time": round(c["time"], 3),
                "strength": round(min(max(c["strength"], 0.0), 1.0), 3),
                "reason": c["reason"],
            }
            for c in picked
        ],
        key=lambda c: c["time"],
    )


def _motion_peaks(
    intervals: list[dict[str, float]], max_intensity: float
) -> list[dict[str, float]]:
    """Local maxima of motion intensity above `MOTION_PEAK_THRESHOLD`."""
    if not intervals or max_intensity <= 0.0:
        return []
    peaks: list[dict[str, float]] = []
    for i, interval in enumerate(intervals):
        intensity = interval["intensity"]
        if intensity / max_intensity < MOTION_PEAK_THRESHOLD:
            continue
        prev_intensity = intervals[i - 1]["intensity"] if i > 0 else intensity
        next_intensity = (
            intervals[i + 1]["intensity"] if i + 1 < len(intervals) else intensity
        )
        if intensity >= prev_intensity and intensity >= next_intensity:
            peaks.append(interval)
    return peaks


def _dedupe(
    candidates: list[dict[str, Any]], window: float
) -> list[dict[str, Any]]:
    """Merge candidates that fall within `window` of each other, keeping the
    strongest. Deterministic: ties keep the earlier time."""
    ordered = sorted(candidates, key=lambda c: (c["time"], c["strength"]))
    merged: list[dict[str, Any]] = []
    for candidate in ordered:
        bucket = next(
            (m for m in merged if abs(m["time"] - candidate["time"]) <= window),
            None,
        )
        if bucket is None:
            merged.append(dict(candidate))
            continue
        if candidate["strength"] > bucket["strength"]:
            bucket["strength"] = candidate["strength"]
        if candidate["reason"] != bucket["reason"]:
            bucket["reason"] = "beat+motion"
    return merged


def _spread(
    candidates: list[dict[str, Any]], gap: float, limit: int
) -> list[dict[str, Any]]:
    """Greedily pick the strongest candidates while keeping them >= `gap`
    apart, up to `limit`. Sorts results by time afterwards (caller sorts)."""
    ordered = sorted(candidates, key=lambda c: -c["strength"])
    picked: list[dict[str, Any]] = []
    for candidate in ordered:
        if any(abs(c["time"] - candidate["time"]) < gap for c in picked):
            continue
        picked.append(candidate)
        if len(picked) >= limit:
            break
    return picked


def _cut_points(
    shots: list[dict[str, float]], duration: float
) -> list[float]:
    points = sorted({shot["end_time"] for shot in shots})
    return [round(t, 3) for t in points if 0.0 < t < duration]


def _shot_at(
    shots: list[dict[str, float]], time: float
) -> dict[str, float] | None:
    for shot in shots:
        if shot["start_time"] <= time < shot["end_time"]:
            return shot
    for shot in shots:
        if abs(shot["end_time"] - time) < 1e-6:
            return shot
    return None


def _normalize_scenes(
    scenes: list[dict[str, Any]],
) -> list[dict[str, float]]:
    normalized = sorted(
        (
            {
                "start_time": max(_safe_float(s.get("start_time")), 0.0),
                "end_time": max(_safe_float(s.get("end_time")), 0.0),
            }
            for s in scenes
        ),
        key=lambda s: s["start_time"],
    )
    return [
        {
            "start_time": max(s["start_time"], 0.0),
            "end_time": max(s["end_time"], s["start_time"]),
        }
        for s in normalized
    ]


def _normalize_interval(interval: dict[str, Any]) -> dict[str, float]:
    intensity = _safe_float(interval.get("intensity"))
    return {
        "t": max(_safe_float(interval.get("t")), 0.0),
        "intensity": intensity if math.isfinite(intensity) else 0.0,
    }


def _infer_duration(
    scenes: list[dict[str, Any]],
    intervals: list[dict[str, Any]],
    beat_times: list[float],
) -> float:
    ends = [
        _safe_float(s.get("end_time"))
        for s in scenes
        if _safe_float(s.get("end_time")) > 0.0
    ]
    ends += [
        _safe_float(i.get("t")) for i in intervals if _safe_float(i.get("t")) > 0.0
    ]
    ends += [t for t in beat_times if t > 0.0]
    return max(ends, default=0.0)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = _safe_float(value)
    return round(parsed, 1) if parsed else None
