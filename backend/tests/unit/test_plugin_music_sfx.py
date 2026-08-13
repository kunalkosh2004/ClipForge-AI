import pytest

from clipforge.directing.domain.blueprint import TimelineEvent
from clipforge.plugins.application.plugins.music import MusicPlugin
from clipforge.plugins.application.plugins.sfx import SfxPlugin
from tests.unit._render_ctx import make_ctx


def _event(track: str, type: str, parameters: dict | None = None):
    return TimelineEvent(
        track=track, type=type, timestamp=2.0, parameters=parameters or {}
    )


@pytest.mark.asyncio
async def test_music_sets_path_and_clamps_volume() -> None:
    ctx = make_ctx()
    await MusicPlugin().apply(
        ctx,
        [
            _event("music", "music", {"path": "/sounds/bed.wav", "volume_db": 99.0}),
        ],
    )
    assert ctx.music_path == "/sounds/bed.wav"
    assert ctx.music_volume_db == 6.0


@pytest.mark.asyncio
async def test_music_ignores_events_without_path() -> None:
    ctx = make_ctx()
    await MusicPlugin().apply(ctx, [_event("music", "track")])
    assert ctx.music_path is None
    assert ctx.music_volume_db is None


@pytest.mark.asyncio
async def test_sfx_appends_trigger_with_kind_defaulting() -> None:
    ctx = make_ctx()
    await SfxPlugin().apply(
        ctx,
        [
            _event("sfx", "sfx", {"kind": "boom", "volume_db": -3.0}),
            _event("sfx", "boom"),  # type drives the default kind
            _event("sfx", "whoosh", {"kind": "whoosh"}),
        ],
    )
    assert ctx.sfx_triggers == [
        {"kind": "boom", "time": 2.0, "volume_db": -3.0},
        {"kind": "boom", "time": 2.0, "volume_db": 0.0},
        {"kind": "whoosh", "time": 2.0, "volume_db": 0.0},
    ]


@pytest.mark.asyncio
async def test_sfx_ignores_unknown_kinds() -> None:
    ctx = make_ctx()
    await SfxPlugin().apply(ctx, [_event("sfx", "sfx", {"kind": "laser"})])
    assert ctx.sfx_triggers == [{"kind": "whoosh", "time": 2.0, "volume_db": 0.0}]
