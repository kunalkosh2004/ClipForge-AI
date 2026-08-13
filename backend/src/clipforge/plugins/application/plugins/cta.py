"""CTA plugin: call-to-action text from the cta track."""

from __future__ import annotations

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import str_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin


class CtaPlugin(RendererPlugin):
    track = "cta"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("cta", "call_to_action"):
                continue
            text = str_param(event.parameters, "text") or str_param(
                event.parameters, "cta"
            )
            if text:
                ctx.cta_text = text[:80]
