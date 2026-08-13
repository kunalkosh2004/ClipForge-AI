import statistics

from clipforge.common.ports import ClipCandidate, EditingPlan
from clipforge.common.times import parse_timestamp

MIN_CLIP_SECONDS = 20.0
MAX_CLIP_SECONDS = 45.0
OVERLAP_GUARD_SECONDS = 1.0


def normalize_editing_plan(
    plan: EditingPlan,
    duration_seconds: float | None,
    target_duration: float | None = None,
) -> EditingPlan:
    """Deterministic director pass over the AI's raw plan.

    - Normalizes start/end to numeric seconds and clamps them into the video.
    - Drops empty clips, sorts by start, and de-dupes near-identical times.
    - Enforces the 20-45s platform window where possible, preferring the
      preset's `target_duration` when extending short clips.
    - Sanitizes viral_score to 0-100 and derives a plan-level virality index.
    """
    duration = duration_seconds or float("inf")
    preferred = _preferred_duration(target_duration)

    cleaned: list[ClipCandidate] = []
    last_end: float | None = None
    for clip in sorted(plan.clips, key=_clip_start):
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
            ClipCandidate(
                start_time=round(start, 3),
                end_time=round(end, 3),
                hook=clip.hook,
                why_it_is_engaging=clip.why_it_is_engaging,
                viral_score=_sanitize_viral_score(clip.viral_score),
                emotion=clip.emotion,
                category=clip.category,
                thumbnail_text=clip.thumbnail_text,
                emphasis_times=_clip_local_times(clip.emphasis_times, end - start),
                emoji_triggers=_sanitize_emoji_triggers(
                    clip.emoji_triggers, end - start
                ),
                cta_text=clip.cta_text,
                hook_text=clip.hook_text,
            )
        )
        last_end = end

    filled = _extend_short_clips(cleaned, duration, preferred)

    return EditingPlan(
        preset=plan.preset,
        clips=filled,
        thumbnail_text=plan.thumbnail_text,
        virality_index=_virality_index(filled),
        preset_confidence=plan.preset_confidence,
        style=plan.style,
    )


def _preferred_duration(target_duration: float | None) -> float:
    """Clamp the preset's ideal clip length into the platform window."""
    if target_duration is None:
        return MIN_CLIP_SECONDS
    return _clamp(float(target_duration), MIN_CLIP_SECONDS, MAX_CLIP_SECONDS)


def _extend_short_clips(
    clips: list[ClipCandidate],
    duration: float,
    preferred: float = MIN_CLIP_SECONDS,
) -> list[ClipCandidate]:
    """Extend clips shorter than the platform floor forward into the gap that
    separates them from the next clip, up to the preset's preferred length."""
    if not clips:
        return clips

    result: list[ClipCandidate] = []
    for index, clip in enumerate(clips):
        start, end = float(clip.start_time), float(clip.end_time)
        if end - start >= MIN_CLIP_SECONDS:
            result.append(clip)
            continue

        upper_bound = clips[index + 1].start_time if index + 1 < len(clips) else duration
        upper_bound = min(upper_bound - OVERLAP_GUARD_SECONDS, duration)
        target_end = min(start + preferred, start + MAX_CLIP_SECONDS)
        end = min(target_end, upper_bound)
        if end <= start:
            end = start + MIN_CLIP_SECONDS
        clip_duration = round(min(end, duration), 3) - start
        result.append(
            ClipCandidate(
                start_time=clip.start_time,
                end_time=round(min(end, duration), 3),
                hook=clip.hook,
                why_it_is_engaging=clip.why_it_is_engaging,
                viral_score=clip.viral_score,
                emotion=clip.emotion,
                category=clip.category,
                thumbnail_text=clip.thumbnail_text,
                emphasis_times=_clip_local_times(clip.emphasis_times, clip_duration),
                emoji_triggers=_sanitize_emoji_triggers(
                    clip.emoji_triggers, clip_duration
                ),
                cta_text=clip.cta_text,
                hook_text=clip.hook_text,
            )
        )
    return result


def _clip_start(clip: ClipCandidate) -> float:
    return parse_timestamp(clip.start_time)


def _sanitize_viral_score(score: float) -> float:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return 0.0
    return round(min(max(value, 0.0), 100.0), 1)


def _virality_index(clips: list[ClipCandidate]) -> float:
    if not clips:
        return 0.0
    return round(statistics.mean(c.viral_score for c in clips), 1)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _clip_local_times(times: list[float], duration: float) -> list[float]:
    """Keep emphasis times inside the clip (clip-local seconds), dedupe, sort."""
    if not times:
        return []
    seen: set[float] = set()
    result: list[float] = []
    for t in times:
        try:
            value = float(t)
        except (TypeError, ValueError):
            continue
        if not (0.0 < value < duration):
            continue
        value = round(value, 3)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return sorted(result)[:8]


def _sanitize_emoji_triggers(
    triggers: list, duration: float
) -> list[dict]:
    """Drop malformed/out-of-window emoji triggers, keep clip-local times."""
    if not triggers:
        return []
    result: list[dict] = []
    for trigger in triggers:
        if isinstance(trigger, dict):
            emoji = trigger.get("emoji")
            raw_time = trigger.get("time", 0.0)
        else:
            emoji = getattr(trigger, "emoji", None)
            raw_time = getattr(trigger, "time", 0.0)
        if not emoji or not isinstance(emoji, str):
            continue
        try:
            value = round(float(raw_time), 3)
        except (TypeError, ValueError):
            continue
        if not (0.0 <= value < duration):
            continue
        result.append({"emoji": emoji[:8], "time": value})
    return result
