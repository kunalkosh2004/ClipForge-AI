"""SFX plugin: sound-effect hits from the sfx track."""

from __future__ import annotations

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import float_param, str_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin

SFX_KINDS = frozenset({"whoosh", "boom", "hit", "ding"})


class SfxPlugin(RendererPlugin):
    track = "sfx"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("sfx", "whoosh", "boom"):
                continue
            kind = str_param(event.parameters, "kind")
            if kind not in SFX_KINDS:
                kind = "whoosh" if event.type != "boom" else "boom"
            ctx.sfx_triggers.append(
                {
                    "kind": kind,
                    "time": event.timestamp,
                    "volume_db": float_param(event.parameters, "volume_db", 0.0),
                }
            )
