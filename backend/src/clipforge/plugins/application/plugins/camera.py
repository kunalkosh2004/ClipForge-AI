"""Camera plugin: turns punch-in / push-in events into zoom keyframes."""

from __future__ import annotations

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import float_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin
from clipforge.rendering.domain.zoom import ZoomKeyframe

# Default punch strength when the event does not say how hard to push in.
DEFAULT_STRENGTH = 0.15
DEFAULT_DURATION = 0.5
MAX_STRENGTH = 0.5


class CameraPlugin(RendererPlugin):
    track = "camera"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("punch_in", "push_in", "zoom"):
                continue
            strength = min(
                max(
                    float_param(
                        event.parameters,
                        "strength",
                        float_param(event.parameters, "scale", DEFAULT_STRENGTH),
                    ),
                    0.0,
                ),
                MAX_STRENGTH,
            )
            if strength <= 0.0:
                continue
            duration = max(float_param(event.parameters, "duration", DEFAULT_DURATION), 0.1)
            ctx.zoom_keyframes.append(
                ZoomKeyframe(time=event.timestamp, scale=1.0 + strength)
            )
            ctx.zoom_keyframes.append(
                ZoomKeyframe(
                    time=min(event.timestamp + duration, ctx.clip_duration),
                    scale=1.0,
                )
            )
