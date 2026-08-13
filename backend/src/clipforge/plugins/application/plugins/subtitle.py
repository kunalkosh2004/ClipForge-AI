"""Subtitle plugin: applies timeline caption directives to the clip.

Tracks: `subtitle`. Events like a `style` / `caption` change contribute
caption updates (colors, animation, theme, highlight words) on top of the
preset baseline and the blueprint's global subtitle theme.
"""

from __future__ import annotations

from typing import Any

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.lyrics.application.theme import VALID_THEMES, normalize_animation
from clipforge.plugins.application.plugins._helpers import (
    colors_from,
    float_param,
    str_param,
)
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin

CAPTION_COLOR_KEYS = ("active_color", "muted_color", "outline_color")


class SubtitlePlugin(RendererPlugin):
    track = "subtitle"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            self._apply_event(ctx, event)

    def _apply_event(self, ctx: RenderContext, event: TimelineEvent) -> None:
        if event.type not in ("style", "caption", "theme"):
            return
        parameters = event.parameters

        colors = colors_from(parameters)
        if colors:
            for index, key in enumerate(CAPTION_COLOR_KEYS):
                if index < len(colors):
                    ctx.caption_updates[key] = colors[index]

        animation = _animation_value(parameters)
        if animation:
            ctx.caption_updates["animation"] = animation

        size = float_param(parameters, "font_size", 0.0)
        if size > 0.0:
            ctx.caption_updates["font_size_scale"] = round(min(size / 1000.0, 0.1), 5)

        theme = str_param(parameters, "theme") or str_param(parameters, "style_name")
        if theme:
            ctx.caption_theme = _theme_from_name(theme)

        highlights = parameters.get("highlight_words")
        if isinstance(highlights, list):
            ctx.caption_highlight_words = [
                str(w) for w in highlights if isinstance(w, str) and w
            ]


def _animation_value(parameters: dict[str, Any]) -> str | None:
    raw = str_param(parameters, "animation") or str_param(parameters, "word_animation")
    if not raw:
        return None
    try:
        return normalize_animation(raw)
    except ValueError:
        return None


def _theme_from_name(theme: str) -> str | None:
    """Map a style/theme name to a known MotionCaption theme, like the
    blueprint hint does (substring match on the canonical names)."""
    lowered = theme.lower()
    for name in VALID_THEMES:
        if name in lowered:
            return name
    return None
