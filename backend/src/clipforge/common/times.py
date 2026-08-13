from typing import Any


def parse_timestamp(value: Any) -> float:
    """Convert a clip timestamp to seconds.

    Accepts numeric seconds or "MM:SS" / "HH:MM:SS" strings (as returned by
    Gemini-style clip plans).
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        parts = value.strip().split(":")
        try:
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + float(part)
            return seconds
        except ValueError:
            pass
    raise ValueError(f"invalid timestamp value: {value!r}")


def clip_time(clip: dict[str, Any], key: str, fallback_key: str | None = None) -> float:
    """Read a timestamp key from a clip dict, falling back to an alternate key."""
    if key in clip:
        return parse_timestamp(clip[key])
    if fallback_key is not None and fallback_key in clip:
        return parse_timestamp(clip[fallback_key])
    raise ValueError(f"missing clip timestamp key: {key}")
