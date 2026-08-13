import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.transition import TransitionPlugin
from tests.unit._render_ctx import make_ctx


def _event(type: str, duration: float = 0.5):
    return TimelineEvent(
        track="transition",
        type=type,
        timestamp=0.0,
        duration=duration,
        parameters={"type": "fade"},
    )


@pytest.mark.asyncio
async def test_transition_records_plan_without_applying_filters() -> None:
    ctx = make_ctx()
    plugin = TransitionPlugin()
    await plugin.apply(ctx, [_event("fade", 0.5)])
    assert ctx.transition == {
        "type": "fade",
        "duration": 0.5,
        "easing": "smoothstep",
        "reason": "",
    }
    assert ctx.grade_filters == []
    assert ctx.zoom_keyframes == []


@pytest.mark.asyncio
async def test_last_transition_event_wins() -> None:
    ctx = make_ctx()
    plugin = TransitionPlugin()
    await plugin.apply(
        ctx,
        [
            _event("fade", 0.3),
            TimelineEvent(
                track="transition",
                type="slide",
                timestamp=0.0,
                duration=0.6,
                parameters={"type": "slide"},
            ),
        ],
    )
    assert ctx.transition["duration"] == 0.6
    assert ctx.transition["type"] == "slide"
