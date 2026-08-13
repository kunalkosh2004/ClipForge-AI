"""Transition plugin: records boundary transitions for the M6 assembler.

Per-clip renders never apply transitions (they sit on clip boundaries), so
`apply` only records the event on the context. The M6 final-cut assembler
will read `ctx.transition` / `FilterBatch.transition` and generate the
clip-to-clip filter chain.
"""

from __future__ import annotations

from typing import Any

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import str_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin


class TransitionPlugin(RendererPlugin):
    track = "transition"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            ctx.transition = self._plan(event)

    def _plan(self, event: TimelineEvent) -> dict[str, Any]:
        return {
            "type": str_param(event.parameters, "type") or event.type,
            "duration": event.duration,
            "easing": str_param(event.parameters, "easing", "smoothstep"),
            "reason": event.reason,
        }
