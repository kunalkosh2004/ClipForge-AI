import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.subtitle import SubtitlePlugin
from tests.unit._render_ctx import make_ctx


def _event(type: str, parameters: dict | None = None):
    return TimelineEvent(
        track="subtitle", type=type, timestamp=0.0, parameters=parameters or {}
    )


@pytest.mark.asyncio
async def test_style_event_maps_colors_animation_theme_highlights() -> None:
    ctx = make_ctx()
    plugin = SubtitlePlugin()
    await plugin.apply(
        ctx,
        [
            _event(
                "style",
                {
                    "colors": ["#FFD700", "9E9E9E", "000000"],
                    "animation": "highlight",
                    "theme": "Cinematic Slow",
                    "highlight_words": ["moment", "everything"],
                },
            )
        ],
    )
    assert ctx.caption_updates == {
        "active_color": "FFD700",
        "muted_color": "9E9E9E",
        "outline_color": "000000",
        "animation": "glow",  # "highlight" maps to the glow strategy
    }
    assert ctx.caption_theme == "cinematic"
    assert ctx.caption_highlight_words == ["moment", "everything"]


@pytest.mark.asyncio
async def test_invalid_colors_and_animation_are_ignored() -> None:
    ctx = make_ctx()
    plugin = SubtitlePlugin()
    await plugin.apply(
        ctx,
        [
            _event(
                "caption",
                {"colors": ["#XYZ123", "nope"], "animation": "spin", "word_animation": "jump"},
            )
        ],
    )
    assert ctx.caption_updates == {}
    assert ctx.caption_theme is None


@pytest.mark.asyncio
async def test_font_size_maps_to_scale() -> None:
    ctx = make_ctx()
    plugin = SubtitlePlugin()
    await plugin.apply(ctx, [_event("style", {"font_size": 50})])
    assert ctx.caption_updates["font_size_scale"] == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_non_caption_types_ignored() -> None:
    ctx = make_ctx()
    plugin = SubtitlePlugin()
    await plugin.apply(ctx, [_event("wipe")])
    assert ctx.caption_updates == {}
