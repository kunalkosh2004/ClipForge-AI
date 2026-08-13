"""Lyrics application layer: preset/style → MotionCaption theme mapping."""

from __future__ import annotations

PRESET_THEMES: dict[str, str] = {
    "podcast": "clean",
    "storytelling": "cinematic",
    "tutorial": "clean",
    "reaction": "sport",
    "commentary": "news",
    "motivational": "music_video",
    "mrbeast": "sport",
    "hormozi": "sport",
    "minimal": "clean",
    "gaming": "music_video",
    "documentary": "cinematic",
    "business": "news",
}

DEFAULT_THEME = "clean"

VALID_THEMES = frozenset(("clean", "cinematic", "music_video", "news", "sport"))

_ANIMATION_ALIASES: dict[str, str] = {
    "sweep": "karaoke",
    "word": "karaoke",
    "word-by-word": "karaoke",
    "typewriter": "karaoke",
    "karaoke": "karaoke",
    "highlight": "glow",
    "glitch": "bounce",
    "bounce": "bounce",
    "fade": "fade",
    "pop": "pop",
    "slide": "slide",
    "glow": "glow",
    "scale": "scale",
    "spring": "spring",
    "elastic": "elastic",
    "overshoot": "overshoot",
    "ripple": "ripple",
    "rotate": "rotate",
    "blur": "blur",
    "pulse": "pulse",
    "none": "none",
}


def theme_name_for(preset: str | None, explicit: str | None = None) -> str:
    """Resolve the MotionCaption theme for a ClipForge preset.

    An explicit theme name (validated against the built-ins) wins; otherwise
    the preset mapping is used; unknown presets fall back to ``clean``.
    """
    if explicit:
        return explicit if explicit in VALID_THEMES else DEFAULT_THEME
    if preset:
        return PRESET_THEMES.get(preset, DEFAULT_THEME)
    return DEFAULT_THEME


def animation_strategy(animation: str | None, karaoke: bool = False) -> str:
    """Map a ClipForge caption animation label to a MotionCaption strategy.

    Karaoke/word-by-word/typewriter all map to the word-timed ``karaoke``
    strategy; unknown labels pass through so future MotionCaption templates
    remain usable without a mapping change.
    """
    if karaoke:
        return "karaoke"
    if animation:
        return _ANIMATION_ALIASES.get(animation.lower(), animation.lower())
    return "fade"


def normalize_animation(value: str | None) -> str | None:
    """Canonical MotionCaption strategy for a known label, or None.

    Unlike :func:`animation_strategy` this rejects unknown labels so an
    AI-provided animation name only takes effect when it maps cleanly.
    """
    if not value:
        return None
    lowered = value.lower()
    if lowered in _ANIMATION_ALIASES:
        return animation_strategy(lowered, karaoke=False)
    return None


def accent_hex(value: str | None) -> str | None:
    """Normalize a caption color to a 6-digit uppercase hex, or None."""
    if not value:
        return None
    cleaned = value.lstrip("#")
    return cleaned.upper() if len(cleaned) == 6 else None
