"""Color plugin: turns color-grading events into ffmpeg grade filters.

Serves the ``color`` track and aliases the blueprint's ``effects`` track.
Only well-supported, deterministic filters are emitted: eq (brightness /
contrast / saturation / vibrance), colorbalance (temperature), noise (film
grain) and vignette. Bloom / glow are intentionally left for a future
plugin pass and are ignored here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import float_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin

_GRADERS: tuple[tuple[str, Callable[[float], str]], ...] = (
    ("brightness", lambda v: f"eq=brightness={_clamp(v, 1.0):.3f}"),
    ("contrast", lambda v: f"eq=contrast={_clamp(v, 1.0):.3f}"),
    ("saturation", lambda v: f"eq=saturation={_clamp(v, 2.0):.3f}"),
    ("vibrance", lambda v: f"eq=saturation={_clamp(1.0 + v, 2.0):.3f}"),
    ("film_grain", lambda v: f"noise=alls={int(round(_clamp(v, 1.0) * 70))}:allf=t"),
    ("vignette", lambda v: f"vignette=angle=PI/{4 + (2 if v > 0 else 0)}"),
)


class ColorPlugin(RendererPlugin):
    track = "color"

    async def apply(self, ctx: RenderContext, events: list[TimelineEvent]) -> None:
        for event in events:
            if event.type not in ("grade", "color", "effects"):
                continue
            self._grade(ctx, event.parameters)

    def _grade(self, ctx: RenderContext, parameters: dict[str, Any]) -> None:
        for key, builder in _GRADERS:
            value = float_param(parameters, key)
            if value == 0.0:
                continue
            ctx.grade_filters.append(builder(value))

        temperature = float_param(parameters, "temperature")
        if temperature != 0.0:
            warm = _clamp(temperature, 0.5)
            ctx.grade_filters.append(
                f"colorbalance=rs={warm:.3f}:gs={warm / 2:.3f}:bs={-warm:.3f}"
            )


def _clamp(value: float, limit: float) -> float:
    return min(max(value, -limit), limit)
