"""Overlay plugin: lower-thirds / branding from the overlay track."""

from __future__ import annotations

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import str_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin


class OverlayPlugin(RendererPlugin):
    track = "overlay"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("lower_third", "branding", "overlay"):
                continue
            text = str_param(event.parameters, "text") or str_param(
                event.parameters, "title"
            )
            if text:
                ctx.lower_third_text = text
