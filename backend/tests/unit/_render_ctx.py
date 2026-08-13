from clipforge.clips.domain.entities import Clip
from clipforge.common.ids import uuid7
from clipforge.plugins.domain.spec import RenderContext
from clipforge.rendering.domain.styles import RenderStyle


def make_clip(start: float = 0.0, end: float = 6.0) -> Clip:
    return Clip(
        id=uuid7(),
        video_id=uuid7(),
        project_id=uuid7(),
        title="Test Clip",
        start_seconds=start,
        end_seconds=end,
        duration_seconds=end - start,
        storage_key="clips/source.mp4",
        status="ready",
        format="9:16",
    )


def make_ctx(
    start: float = 0.0, end: float = 6.0, style: RenderStyle | None = None
) -> RenderContext:
    clip = make_clip(start, end)
    return RenderContext(
        clip=clip,
        canvas=(540, 960),
        clip_start=start,
        clip_end=end,
        clip_duration=end - start,
        preset="default",
        style=style or RenderStyle(),
        words=[],
    )
