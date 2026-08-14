import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.color import ColorPlugin, _glow_bloom_graph
from tests.unit._render_ctx import make_ctx


def _event(type: str, parameters: dict | None = None):
    return TimelineEvent(
        track="color", type=type, timestamp=0.0, parameters=parameters or {}
    )


@pytest.mark.asyncio
async def test_grade_emits_filters_for_present_params() -> None:
    ctx = make_ctx()
    plugin = ColorPlugin()
    await plugin.apply(
        ctx,
        [
            _event(
                "grade",
                {
                    "brightness": 0.1,
                    "contrast": -0.2,
                    "saturation": 1.4,
                    "film_grain": 0.5,
                    "vignette": 0.8,
                    "temperature": 0.3,
                },
            )
        ],
    )
    assert ctx.grade_filters == [
        "eq=brightness=0.100",
        "eq=contrast=0.800",  # -0.2 on the -1..1 offset -> eq's 1.0-neutral scale
        "eq=saturation=1.400",
        "noise=alls=35:allf=t",
        "vignette=angle=PI/6",
        "colorbalance=rs=0.300:gs=0.150:bs=-0.300",
    ]


@pytest.mark.asyncio
async def test_zero_params_ignored_but_glow_bloom_emitted() -> None:
    ctx = make_ctx()
    plugin = ColorPlugin()
    await plugin.apply(
        ctx,
        [_event("grade", {"brightness": 0.0, "bloom": 0.9, "glow": 0.5})],
    )
    assert len(ctx.grade_filters) == 1
    graph = ctx.grade_filters[0]
    assert "split=" in graph
    assert "gblur" in graph
    assert "blend=all_mode=screen" in graph
    assert "all_opacity=0.225" in graph  # 0.05 + 0.35 * 0.5 glow


@pytest.mark.asyncio
async def test_values_are_clamped() -> None:
    ctx = make_ctx()
    plugin = ColorPlugin()
    await plugin.apply(
        ctx,
        [_event("grade", {"brightness": 5.0, "saturation": 10.0, "temperature": 3.0})],
    )
    assert ctx.grade_filters == [
        "eq=brightness=1.000",
        "eq=saturation=2.000",
        "colorbalance=rs=0.500:gs=0.250:bs=-0.500",
    ]


def test_glow_bloom_graph_combines_both() -> None:
    graph = _glow_bloom_graph(0.5, 0.9)
    assert graph is not None
    assert graph.count("split=") == 1
    assert "split=3" in graph
    assert "gblur=sigma=9.0" in graph  # 2 + 14 * 0.5
    assert "gblur=sigma=18.4" in graph  # 4 + 16 * 0.9
    # two blends chained: glow into bloom
    assert graph.count("blend=all_mode=screen") == 2


def test_glow_bloom_graph_glow_only() -> None:
    graph = _glow_bloom_graph(0.5, 0.0)
    assert graph is not None
    assert "split=2" in graph
    assert graph.count("blend=all_mode=screen") == 1


def test_glow_bloom_graph_bloom_only() -> None:
    graph = _glow_bloom_graph(0.0, 0.9)
    assert graph is not None
    assert "split=2" in graph
    assert "curves=all=" in graph
    assert graph.count("blend=all_mode=screen") == 1


def test_glow_bloom_graph_none_when_zero() -> None:
    assert _glow_bloom_graph(0.0, 0.0) is None
    assert _glow_bloom_graph(-1.0, -1.0) is None
