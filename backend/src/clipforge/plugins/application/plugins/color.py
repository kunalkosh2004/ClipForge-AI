"""Color plugin: turns color-grading events into ffmpeg grade filters.

Serves the ``color`` track and aliases the blueprint's ``effects`` track.
Only well-supported, deterministic filters are emitted: eq (brightness /
contrast / saturation / vibrance), colorbalance (temperature), noise (film
grain) and vignette. Bloom / glow are implemented as a screen-blend pass
over a blurred copy of the frame (split + gblur/curves + blend), emitted as
a single labeled subgraph so the composite's comma-joined filter chain stays
valid.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins._helpers import float_param
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin

_GRADERS: tuple[tuple[str, Callable[[float], str]], ...] = (
    ("brightness", lambda v: f"eq=brightness={_clamp(v, 1.0):.3f}"),
    # ffmpeg's eq filter uses 1.0 as neutral contrast, so shift the -1..1
    # input onto that scale (same pattern as vibrance).
    ("contrast", lambda v: f"eq=contrast={_clamp(1.0 + v, 2.0):.3f}"),
    ("saturation", lambda v: f"eq=saturation={_clamp(v, 2.0):.3f}"),
    ("vibrance", lambda v: f"eq=saturation={_clamp(1.0 + v, 2.0):.3f}"),
    ("film_grain", lambda v: f"noise=alls={int(round(_clamp(v, 1.0) * 70))}:allf=t"),
    ("vignette", lambda v: f"vignette=angle=PI/{4 + (2 if v > 0 else 0)}"),
)

# Highlight curve used by the bloom pass: keeps mids/highs, soft-crushes darks
# so only bright areas contribute to the glow.
_BLOOM_CURVES = "curves=all='0/0 0.45/0.05 0.6/0.35 1/1'"


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

        graph = _glow_bloom_graph(
            float_param(parameters, "glow"),
            float_param(parameters, "bloom"),
        )
        if graph and not any("split=" in f for f in ctx.grade_filters):
            ctx.grade_filters.append(graph)


def _glow_bloom_graph(glow: float, bloom: float) -> str | None:
    """Screen-blend glow/bloom subgraph, or None when both strengths are 0.

    The graph is emitted as ONE element of ``grade_filters``: the composite
    joins filters with commas, so the final ``,setsar=1[base]`` continues the
    last ``blend`` chain. ``glow``/``bloom`` are 0..1 strengths.
    """
    if glow <= 0.0 and bloom <= 0.0:
        return None
    glow = min(max(glow, 0.0), 1.0)
    bloom = min(max(bloom, 0.0), 1.0)

    g_sigma = round(2.0 + 14.0 * glow, 2)
    g_opacity = round(0.05 + 0.35 * glow, 3)
    b_sigma = round(4.0 + 16.0 * bloom, 2)
    b_opacity = round(0.10 + 0.45 * bloom, 3)

    if glow > 0.0 and bloom > 0.0:
        return (
            "split=3[g_a][g_b][g_c];"
            f"[g_b]gblur=sigma={g_sigma}[g_glow];"
            f"[g_c]{_BLOOM_CURVES},gblur=sigma={b_sigma}[g_bloom];"
            f"[g_a][g_glow]blend=all_mode=screen:all_opacity={g_opacity}[g_x];"
            f"[g_x][g_bloom]blend=all_mode=screen:all_opacity={b_opacity}"
        )
    if glow > 0.0:
        return (
            "split=2[g_a][g_b];"
            f"[g_b]gblur=sigma={g_sigma}[g_glow];"
            f"[g_a][g_glow]blend=all_mode=screen:all_opacity={g_opacity}"
        )
    return (
        "split=2[b_a][b_b];"
        f"[b_b]{_BLOOM_CURVES},gblur=sigma={b_sigma}[b_bloom];"
        f"[b_a][b_bloom]blend=all_mode=screen:all_opacity={b_opacity}"
    )


def _clamp(value: float, limit: float) -> float:
    return min(max(value, -limit), limit)
