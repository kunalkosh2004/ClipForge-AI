"""Emoji plugin: emoji pop-ins from the emoji track."""

from __future__ import annotations

from typing import Any

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import float_param, str_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin


class EmojiPlugin(RendererPlugin):
    track = "emoji"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("emoji", "pop"):
                continue
            emoji = str_param(event.parameters, "emoji")
            if not emoji:
                continue
            ctx.overlay_events.append(
                {
                    "emoji": emoji[:8],
                    "time": event.timestamp,
                    "duration": max(float_param(event.parameters, "duration", 2.0), 0.1),
                    "x": _positional_param(event.parameters, "x", 0.5),
                    "y": _positional_param(event.parameters, "y", 0.5),
                }
            )


def _positional_param(
    parameters: dict[str, Any], key: str, default: float
) -> float:
    value = float_param(parameters, key, default)
    return min(max(value, 0.0), 1.0)
