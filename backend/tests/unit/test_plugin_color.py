import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.color import ColorPlugin
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
        "eq=contrast=-0.200",
        "eq=saturation=1.400",
        "noise=alls=35:allf=t",
        "vignette=angle=PI/6",
        "colorbalance=rs=0.300:gs=0.150:bs=-0.300",
    ]


@pytest.mark.asyncio
async def test_zero_params_and_unsupported_ignored() -> None:
    ctx = make_ctx()
    plugin = ColorPlugin()
    await plugin.apply(
        ctx,
        [
            _event(
                "grade",
                {"brightness": 0.0, "bloom": 0.9, "glow": 0.5},
            )
        ],
    )
    assert ctx.grade_filters == []


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
