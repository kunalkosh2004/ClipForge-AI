import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.pipeline import (
    PluginRenderPipeline,
    compile_batch,
)
from clipforge.plugins.domain.registry import build_default_registry
from tests.unit._render_ctx import make_ctx


def _event(track: str, type: str, timestamp: float, parameters: dict | None = None):
    return TimelineEvent(
        track=track, type=type, timestamp=timestamp, parameters=parameters or {}
    )


@pytest.mark.asyncio
async def test_pipeline_executes_plugins_into_filter_batch() -> None:
    ctx = make_ctx()
    events = {
        "camera": [_event("camera", "punch_in", 2.0, {"strength": 0.2})],
        "color": [_event("color", "grade", 0.0, {"brightness": 0.1})],
        "emoji": [_event("emoji", "emoji", 1.0, {"emoji": "🔥"})],
        "overlay": [_event("overlay", "lower_third", 0.0, {"text": "Intro"})],
        "sfx": [_event("sfx", "sfx", 3.0, {"kind": "boom"})],
    }
    pipeline = PluginRenderPipeline(build_default_registry())
    batch = await pipeline.render(ctx, events)

    assert any(f.startswith("eq=brightness=") for f in batch.video_filters)
    assert any("scale" in f for f in batch.video_filters)  # camera zoom expr
    assert batch.overlay_events == (
        {"emoji": "🔥", "time": 1.0, "duration": 2.0, "x": 0.5, "y": 0.5},
    )
    assert batch.lower_third_text == "Intro"
    assert batch.sfx_triggers == (
        {"kind": "boom", "time": 3.0, "volume_db": 0.0},
    )


@pytest.mark.asyncio
async def test_pipeline_ignores_unregistered_tracks() -> None:
    ctx = make_ctx()
    events = {"nope": [_event("nope", "x", 1.0)]}
    batch = await PluginRenderPipeline(build_default_registry()).render(ctx, events)
    assert batch.is_empty()


@pytest.mark.asyncio
async def test_pipeline_skips_tracks_without_events() -> None:
    ctx = make_ctx()
    events = {"camera": [_event("camera", "punch_in", 1.0)]}
    batch = await PluginRenderPipeline(build_default_registry()).render(ctx, events)
    assert batch.lower_third_text is None
    assert batch.transition is None


@pytest.mark.asyncio
async def test_pipeline_no_zoom_when_no_camera_events() -> None:
    ctx = make_ctx()
    batch = await PluginRenderPipeline(build_default_registry()).render(ctx, {})
    assert batch.video_filters == ()


def test_compile_batch_empty_context() -> None:
    ctx = make_ctx()
    batch = compile_batch(ctx)
    assert batch.is_empty()


def test_compile_batch_carries_transition_for_assembler() -> None:
    ctx = make_ctx()
    ctx.transition = {"type": "fade", "duration": 0.5}
    batch = compile_batch(ctx)
    assert batch.transition == {"type": "fade", "duration": 0.5}


def test_compile_batch_uses_track_order_for_determinism() -> None:
    pipeline = PluginRenderPipeline(build_default_registry())
    events = {
        "subtitle": [_event("subtitle", "style", 0.0)],
        "camera": [_event("camera", "punch_in", 1.0)],
    }
    ordered = pipeline._track_order(events)
    assert ordered == ["camera", "subtitle"]
