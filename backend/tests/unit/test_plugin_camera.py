import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.camera import CameraPlugin
from tests.unit._render_ctx import make_ctx


def _event(timestamp: float, type: str = "punch_in", parameters: dict | None = None):
    return TimelineEvent(
        track="camera",
        type=type,
        timestamp=timestamp,
        parameters=parameters or {},
    )


@pytest.mark.asyncio
async def test_punch_in_adds_zoom_keyframes() -> None:
    ctx = make_ctx()
    plugin = CameraPlugin()
    await plugin.apply(ctx, [_event(2.0, parameters={"strength": 0.2, "duration": 0.6})])
    keyframes = sorted(ctx.zoom_keyframes, key=lambda k: k.time)
    assert len(keyframes) == 2
    assert keyframes[0].time == 2.0
    assert keyframes[0].scale == pytest.approx(1.2)
    assert keyframes[1].time == pytest.approx(2.6)
    assert keyframes[1].scale == 1.0


@pytest.mark.asyncio
async def test_strength_uses_scale_fallback_and_clamps() -> None:
    ctx = make_ctx()
    plugin = CameraPlugin()
    await plugin.apply(
        ctx,
        [
            _event(1.0, parameters={"scale": 0.1}),
            _event(2.0, parameters={"strength": 2.0}),
            _event(3.0, parameters={"strength": -1.0}),
        ],
    )
    scales = [k.scale for k in ctx.zoom_keyframes]
    assert pytest.approx(1.1) in scales
    assert pytest.approx(1.5) in scales  # clamped to MAX_STRENGTH
    assert not any(k.time == 3.0 for k in ctx.zoom_keyframes)


@pytest.mark.asyncio
async def test_duration_clamped_to_minimum() -> None:
    ctx = make_ctx()
    plugin = CameraPlugin()
    await plugin.apply(ctx, [_event(1.0, parameters={"duration": 0.01})])
    back = sorted(ctx.zoom_keyframes, key=lambda k: k.time)[1]
    assert back.time == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_unknown_types_ignored() -> None:
    ctx = make_ctx()
    plugin = CameraPlugin()
    await plugin.apply(ctx, [_event(1.0, type="whip_pan")])
    assert ctx.zoom_keyframes == []
