"""Blueprint-driven caption theming (M4b).

The AI Director's ``editing_blueprint.global_style.subtitle_theme`` is the
richest caption direction available (colors, animation, highlight words). This
module maps that raw dict onto the caption hints the lyrics layer consumes:
accent/muted/outline colors, an animation strategy, a MotionCaption theme, and
the highlight words used for karaoke emphasis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clipforge.lyrics.application.theme import VALID_THEMES, normalize_animation

__all__ = ["CaptionThemeHint", "caption_theme_hint"]


@dataclass(frozen=True, slots=True)
class CaptionThemeHint:
    """Caption look + emphasis derived from a video's editing blueprint."""

    accent_color: str | None = None
    muted_color: str | None = None
    outline_color: str | None = None
    animation: str | None = None
    theme: str | None = None
    highlight_words: tuple[str, ...] = ()


def caption_theme_hint(blueprint: dict[str, Any] | None) -> CaptionThemeHint:
    """Map ``editing_blueprint`` to caption theming hints.

    Missing or malformed sections degrade to all-None hints so the caller's
    preset defaults win. ``colors`` follow the ClipForge caption order:
    ``[accent, muted, outline]``.
    """
    if not isinstance(blueprint, dict):
        return CaptionThemeHint()
    global_style = blueprint.get("global_style")
    if not isinstance(global_style, dict):
        return CaptionThemeHint()

    subtitle_theme = global_style.get("subtitle_theme")
    theme_data = subtitle_theme if isinstance(subtitle_theme, dict) else {}

    colors = [_hex_color(c) for c in theme_data.get("colors") or [] if _hex_color(c)]
    accent = colors[0] if colors else None
    muted = colors[1] if len(colors) > 1 else None
    outline = colors[2] if len(colors) > 2 else None

    animation = normalize_animation(
        theme_data.get("animation") or theme_data.get("word_animation")
    )

    return CaptionThemeHint(
        accent_color=accent,
        muted_color=muted,
        outline_color=outline,
        animation=animation,
        theme=_theme_from_style_name(global_style.get("style_name")),
        highlight_words=tuple(
            str(word).strip().lower()
            for word in theme_data.get("highlight_words") or []
            if isinstance(word, str) and word.strip()
        ),
    )


def _hex_color(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.lstrip("#")
    return cleaned.upper() if len(cleaned) == 6 else None


def _theme_from_style_name(style_name: Any) -> str | None:
    if not isinstance(style_name, str) or not style_name.strip():
        return None
    lowered = style_name.strip().lower()
    for theme in VALID_THEMES:
        if theme in lowered:
            return theme
    return None
