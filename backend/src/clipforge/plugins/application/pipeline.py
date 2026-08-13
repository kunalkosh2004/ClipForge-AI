"""Plugin render pipeline: execute per-track plugins and compile a batch.

The pipeline is a pure executor: for each track with in-window events it
resolves the plugin from the registry and calls ``apply`` on the shared
context, then compiles the context into the `FilterBatch` the composite
encoder consumes. Plugins never make creative decisions; the blueprint's
events are the only input.
"""

from __future__ import annotations

from typing import Any

from clipforge.directing.domain.blueprint import TRACK_ORDER, TimelineEvent
from clipforge.plugins.application.compile import compile_clip_events
from clipforge.plugins.domain.registry import PluginRegistry
from clipforge.plugins.domain.spec import RenderContext, RendererPlugin
from clipforge.rendering.domain.batch import FilterBatch
from clipforge.rendering.domain.zoom import ZoomEngine, ZoomPlan


class PluginRenderPipeline:
    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def resolve(self, track: str) -> RendererPlugin | None:
        return self._registry.resolve(track)

    async def render(
        self,
        ctx: RenderContext,
        events_by_track: dict[str, list[TimelineEvent]],
    ) -> FilterBatch:
        for track in self._track_order(events_by_track):
            events = events_by_track.get(track)
            if not events:
                continue
            plugin = self._registry.resolve(track)
            if plugin is None:
                continue
            await plugin.apply(ctx, events)
        return compile_batch(ctx)

    def _track_order(
        self, events_by_track: dict[str, list[TimelineEvent]]
    ) -> list[str]:
        ordered = [t for t in TRACK_ORDER if events_by_track.get(t)]
        for track in sorted(events_by_track):
            if track not in ordered:
                ordered.append(track)
        return ordered


def compile_clip_events_for(
    blueprint: dict[str, Any] | None,
    clip_start: float,
    clip_end: float,
) -> dict[str, list[TimelineEvent]]:
    return compile_clip_events(blueprint, clip_start, clip_end)


def compile_batch(ctx: RenderContext) -> FilterBatch:
    """Assemble the final `FilterBatch` from a fully-executed context."""
    video_filters: list[str] = list(ctx.grade_filters)

    zoom_expr = _zoom_expression(ctx)
    if zoom_expr:
        video_filters.append(zoom_expr)

    return FilterBatch(
        video_filters=tuple(video_filters),
        overlay_events=tuple(ctx.overlay_events),
        lower_third_text=ctx.lower_third_text,
        cta_text=ctx.cta_text,
        music_path=ctx.music_path,
        music_volume_db=ctx.music_volume_db,
        sfx_triggers=tuple(ctx.sfx_triggers),
        transition=ctx.transition,
    )


def _zoom_expression(ctx: RenderContext) -> str | None:
    """Zoom filter expr from the style baseline + camera events.

    Returns None when the plan produces no actual zoom (matches the legacy
    renderer's "no zoom" sentinel)."""
    width, height = ctx.canvas
    engine = ZoomEngine(ctx.style.zoom)
    base = engine.build_zoom_plan(ctx.clip_duration, ctx.emphasis_times, ctx.emphasis_times)
    keyframes = list(base.keyframes)
    keyframes.extend(ctx.zoom_keyframes)
    plan = ZoomPlan(keyframes=sorted(keyframes, key=lambda k: k.time))
    expression = plan.to_filter_expr(width, height)
    if expression == f"scale={width}:{height}":
        return None
    return expression
