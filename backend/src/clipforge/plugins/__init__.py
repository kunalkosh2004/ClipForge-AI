"""Renderer plugins: deterministic per-track executors of the blueprint."""

from clipforge.plugins.application.compile import compile_clip_events
from clipforge.plugins.application.pipeline import (
    PluginRenderPipeline,
    compile_batch,
)
from clipforge.plugins.domain.registry import (
    PluginRegistry,
    build_default_registry,
)
from clipforge.plugins.domain.spec import (
    RenderContext,
    RendererPlugin,
)

__all__ = [
    "PluginRegistry",
    "PluginRenderPipeline",
    "RenderContext",
    "RendererPlugin",
    "build_default_registry",
    "compile_batch",
    "compile_clip_events",
]
