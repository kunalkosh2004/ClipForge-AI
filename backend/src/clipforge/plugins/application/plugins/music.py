"""Music plugin: music-bed selection and volume from the music track."""

from __future__ import annotations

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import float_param, str_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin


class MusicPlugin(RendererPlugin):
    track = "music"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("music", "track"):
                continue
            path = str_param(event.parameters, "path")
            if path:
                ctx.music_path = path
            volume = float_param(event.parameters, "volume_db", float("nan"))
            if volume == volume:  # explicit value present (NaN guard)
                ctx.music_volume_db = round(min(max(volume, -40.0), 6.0), 3)
