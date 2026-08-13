import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.cta import CtaPlugin
from clipforge.plugins.application.plugins.emoji import EmojiPlugin
from clipforge.plugins.application.plugins.overlay import OverlayPlugin
from tests.unit._render_ctx import make_ctx


def _event(track: str, type: str, parameters: dict | None = None):
    return TimelineEvent(
        track=track, type=type, timestamp=1.5, parameters=parameters or {}
    )


@pytest.mark.asyncio
async def test_overlay_lower_third_sets_text() -> None:
    ctx = make_ctx()
    await OverlayPlugin().apply(ctx, [_event("overlay", "lower_third", {"text": "Intro"})])
    assert ctx.lower_third_text == "Intro"


@pytest.mark.asyncio
async def test_overlay_ignores_missing_text_and_other_types() -> None:
    ctx = make_ctx()
    await OverlayPlugin().apply(ctx, [_event("overlay", "branding"), _event("overlay", "fade")])
    assert ctx.lower_third_text is None


@pytest.mark.asyncio
async def test_emoji_appends_overlay_event() -> None:
    ctx = make_ctx()
    await EmojiPlugin().apply(
        ctx,
        [_event("emoji", "emoji", {"emoji": "🔥", "x": 0.2, "y": 0.8})],
    )
    assert ctx.overlay_events == [
        {"emoji": "🔥", "time": 1.5, "duration": 2.0, "x": 0.2, "y": 0.8}
    ]


@pytest.mark.asyncio
async def test_emoji_clamps_position_and_ignores_blank() -> None:
    ctx = make_ctx()
    await EmojiPlugin().apply(
        ctx,
        [
            _event("emoji", "emoji", {"emoji": "✨", "x": 3.0, "y": -1.0}),
            _event("emoji", "emoji", {}),
        ],
    )
    assert ctx.overlay_events[0]["x"] == 1.0
    assert ctx.overlay_events[0]["y"] == 0.0
    assert len(ctx.overlay_events) == 1


@pytest.mark.asyncio
async def test_cta_sets_truncated_text() -> None:
    ctx = make_ctx()
    await CtaPlugin().apply(ctx, [_event("cta", "cta", {"text": "Follow for more" * 10})])
    assert len(ctx.cta_text) == 80
    assert ctx.cta_text.startswith("Follow for more")
